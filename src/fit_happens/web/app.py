"""The web application.

Two audiences, deliberately separate surfaces:

* **Recruiters** get a hierarchy - all roles, one role, one candidate - because a hiring team
  runs several roles at once and the old single hard-coded role implied otherwise.
* **Candidates** get one page reached by a token. No account: someone who has just applied
  should not have to create credentials with a company that has not hired them.

Server-rendered Jinja, one process, no build step. Uploads are processed in the background
because a CV takes one to three minutes cold and a browser should not be held open for it.

Do NOT run with --reload when demoing: the reloader restarts the process on any file change and
kills in-flight background tasks. The task state survives in a file, so the page would spin on
work that is never coming back. `tasks.pending()` reaps anything stuck, but the upload still
has to be repeated.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..candidate.answers import AnswerStore
from ..candidate.consent import SCOPES, ConsentStore
from ..feedback import REASONS, FeedbackStore, Rejection
from ..jd.discovery import corpus_stats, duplicates
from ..jd.guard import ALLOWED_FIELDS, check_value
from ..jd.slop import scan_job_ad
from ..slop.response import CASUAL_QUESTION, scan_responses
from ..stages import ORDER as STAGE_ORDER, STAGES, StageStore
from ..store import Run, roles, slugify
from . import tasks

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="Fit Happens")

UPLOADS = Path("data/uploads")
STYLE_PATTERNS = {"stock_phrases", "self_significance", "negative_parallelism", "copula_avoidance",
                  "uniform_rhythm", "rule_of_three", "em_dash_density", "style_divergence"}


def _err(request: Request, message: str, status: int = 404, back: str = "/") -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, "error.html",
                                      {"message": message, "back": back}, status_code=status)


def _cp3_for(slug: str, c):
    """Checkpoint 3, computed at render time - answers arrive long after the pipeline ran, and
    a stored copy would go stale the moment one is edited."""
    answers = AnswerStore(slug).load(c.candidate_id)
    if not answers.submitted:
        return None
    return scan_responses(answers.answers, c.claims, c.employment, c.document.text)


def _response_label(cp3) -> tuple[str, str]:
    if cp3 is None:
        return "PENDING", "grey"
    n = len([f for f in cp3.flags if f.pattern_id not in STYLE_PATTERNS])
    if cp3.verdict.value == "flag_for_human":
        return (f"{n} FLAG" if n == 1 else f"{n} FLAGS"), "red"
    if cp3.verdict.value == "inconclusive":
        return "NOT CORROBORATED", "amber"
    return "LOW RISK", "green"


# ---------------------------------------------------------------- overview


@app.get("/", response_class=HTMLResponse)
def overview(request: Request):
    all_roles = roles()
    everyone = [(r, c) for r in all_roles for c in Run(r["slug"]).candidates()]
    return TEMPLATES.TemplateResponse(request, "overview.html", {
        "roles": all_roles,
        "open_roles": len(all_roles),
        "applicants": sum(r["candidates"] for r in all_roles),
        "needs_review": sum(r["flagged"] for r in all_roles),
        "mean_fit": (sum(c.fit.score for _, c in everyone) / len(everyone)) if everyone else 0.0,
        "top": sorted(everyone, key=lambda rc: -rc[1].fit.score)[:6],
        "nav": "overview",
    })


@app.post("/seed")
def seed_demo(background: BackgroundTasks):
    """One click to a populated demo. The old empty state told a first-time visitor to go and
    run a shell command, which is not an empty state, it is a dead end."""
    from ..demo import seed

    background.add_task(seed)
    return RedirectResponse("/?seeding=1", status_code=303)


# ---------------------------------------------------------------- a role


@app.get("/roles/new", response_class=HTMLResponse)
def new_role_step1(request: Request):
    """Step 1 of 3. Just the advert - asking for everything at once was the problem."""
    return TEMPLATES.TemplateResponse(request, "role_step1.html", {"nav": "roles", "step": 1})


@app.post("/roles/preview", response_class=HTMLResponse)
async def new_role_step2(request: Request):
    """Step 2 of 3. Show her what we extracted BEFORE the role exists.

    Previously she pasted an advert and pressed Create having seen nothing of what we
    understood; the first time she learned what we read was after the fact. Requirements are
    editable here, because our parse is a draft of her intent, not a ruling on it.
    """
    form = await request.form()
    jd_text = str(form.get("jd_text", "")).strip()
    title = str(form.get("title", "")).strip()
    if not jd_text:
        return _err(request, "Paste the advert first - we score against it.", 400, "/roles/new")

    from ..jd.parse import parse_jd

    parsed_title, reqs = parse_jd(jd_text, title)
    _, ad_flags, clarity = scan_job_ad(jd_text)
    return TEMPLATES.TemplateResponse(request, "role_step2.html", {
        "nav": "roles", "step": 2, "title": title or parsed_title, "jd_text": jd_text,
        "requirements": reqs, "clarity": clarity, "allowed": ALLOWED_FIELDS,
        "missing": [f for f in ad_flags if f.pattern_id == "missing_specifics"],
        "hollow": [f for f in ad_flags if f.pattern_id == "hollow_phrase"]})


@app.post("/roles/check")
def check_internal(field_name: str = Form(...), value: str = Form("")):
    """Live guard feedback while the recruiter types an internal criterion.

    Refusing at submit time would be too late to teach anything. Refusing as they type is where
    the compliance story stops being a slide and becomes something they experience.
    """
    r = check_value(field_name, value)
    return JSONResponse({"allowed": r.allowed, "reason": r.reason})


@app.post("/roles/new")
async def create_role(request: Request, background: BackgroundTasks):
    """Step 3: create the role, honouring the requirement edits, and start any CVs processing."""
    form = await request.form()
    title = str(form.get("title", "")).strip()
    jd_text = str(form.get("jd_text", "")).strip()
    if not jd_text:
        return _err(request, "A role needs an advert to score against.", 400, "/roles/new")

    slug, n = slugify(title or "role"), 2
    base = slug
    while Run(slug).exists:
        slug, n = f"{base}-{n}", n + 1

    from ..jd.model import InternalConstraint, JobDescription
    from ..jd.parse import parse_jd

    parsed_title, external = parse_jd(jd_text, title)
    # She reviewed the parse and may have unticked things we got wrong. Our extraction is a
    # draft of her intent, not a ruling on it.
    keep = {int(v) for v in form.getlist("keep") if str(v).isdigit()}
    if keep:
        external = [r for i, r in enumerate(external) if i in keep]

    internal = [
        InternalConstraint(field_name=str(form.get(f"if{i}")), value=str(form.get(f"iv{i}")).strip(),
                           required=bool(form.get(f"ir{i}")))
        for i in range(6)
        if str(form.get(f"if{i}", "")) and str(form.get(f"iv{i}", "")).strip()
    ]
    jd = JobDescription(title=title or parsed_title, external_text=jd_text, internal=internal)
    reqs = external + jd.internal_requirements()
    _, ad_flags, clarity = scan_job_ad(jd_text)
    Run(slug).save_role(jd, reqs, clarity, ad_flags)

    dest = UPLOADS / slug
    for f in form.getlist("files"):
        if not getattr(f, "filename", ""):
            continue
        dest.mkdir(parents=True, exist_ok=True)
        safe = slugify(Path(f.filename).stem) + Path(f.filename).suffix.lower()
        with (dest / safe).open("wb") as out:
            shutil.copyfileobj(f.file, out)
        background.add_task(tasks.process_cv, slug, str(dest / safe), tasks.start(slug, safe))

    return RedirectResponse(f"/role/{slug}", status_code=303)


@app.get("/role/{slug}", response_class=HTMLResponse)
def role(request: Request, slug: str, internal: int = 1, sort: str = "fit",
         filter_by: str = ""):
    run = Run(slug)
    role_data = run.load_role()
    if not role_data:
        return _err(request, "That role does not exist.", 404)
    candidates = run.candidates()
    cp3s = {c.candidate_id: _cp3_for(slug, c) for c in candidates}
    reqs = role_data["requirements"]

    if not internal:
        from ..fit.score import score_fit
        from ..schemas import Requirement

        public = [Requirement(**r) for r in reqs if r["source"] == "external"]
        ids = {r.id for r in public}
        for c in candidates:
            c.fit = score_fit([m for m in c.fit.matches if m.requirement_id in ids], public)
        candidates.sort(key=lambda c: -c.fit.score)

    stages = StageStore(slug)
    stage_of = {c.candidate_id: stages.load(c.candidate_id) for c in candidates}
    if filter_by == "review":
        candidates = [c for c in candidates
                      if c.cp2.verdict.value == "flag_for_human" or c.style.band != "low"]
    elif filter_by == "top":
        candidates = [c for c in candidates if c.fit.score >= 0.55]
    elif filter_by == "waiting":
        candidates = [c for c in candidates if stage_of[c.candidate_id].stage == "questions_sent"]
    elif filter_by == "undecided":
        candidates = [c for c in candidates if not stage_of[c.candidate_id].is_decided]

    keys = {
        "fit": lambda c: -c.fit.score,
        "style": lambda c: {"low": 0, "grey": 1, "high": 2}[c.style.band],
        "claims": lambda c: -len(c.authenticity_flags),
        "name": lambda c: c.display_name.lower(),
    }
    if sort in keys:
        candidates = sorted(candidates, key=keys[sort])

    return TEMPLATES.TemplateResponse(request, "ranking.html", {
        "slug": slug, "role": role_data, "candidates": candidates,
        "stage_of": stage_of, "stages": STAGES, "sort": sort, "filter_by": filter_by,
        "total": len(run.candidates()),
        "use_internal": bool(internal),
        "required_count": sum(1 for r in reqs if r["kind"] == "required"),
        "preferred_count": sum(1 for r in reqs if r["kind"] == "preferred"),
        "internal_count": sum(1 for r in reqs if r["source"] == "internal"),
        "blocked": sum(1 for e in role_data["jd"].get("audit", []) if e["event"] == "internal_constraint_REFUSED"),
        "response_labels": {cid: _response_label(v) for cid, v in cp3s.items()},
        "pending": tasks.pending(slug), "recent": tasks.recent(slug), "nav": "roles",
    })


@app.post("/role/{slug}/upload")
async def upload_cvs(slug: str, background: BackgroundTasks, files: list[UploadFile] = None):
    run = Run(slug)
    if not run.exists:
        return RedirectResponse("/", status_code=303)
    dest = UPLOADS / slug
    dest.mkdir(parents=True, exist_ok=True)
    for f in files or []:
        if not f.filename:
            continue
        safe = slugify(Path(f.filename).stem) + Path(f.filename).suffix.lower()
        target = dest / safe
        with target.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        tid = tasks.start(slug, safe)
        background.add_task(tasks.process_cv, slug, str(target), tid)
    return RedirectResponse(f"/role/{slug}", status_code=303)


@app.post("/role/{slug}/dismiss")
def dismiss_notices(slug: str):
    """Clear finished and failed upload notices. Without this a single old failure sat at the
    top of the page permanently, describing a problem that had already been resolved."""
    tasks.clear_finished(slug)
    return RedirectResponse(f"/role/{slug}", status_code=303)


@app.get("/role/{slug}/status")
def role_status(slug: str):
    """Polled by the ranking page while uploads process."""
    return JSONResponse({"pending": tasks.pending(slug), "recent": tasks.recent(slug)})


@app.get("/role/{slug}/job-ad", response_class=HTMLResponse)
def job_ad(request: Request, slug: str):
    role_data = Run(slug).load_role()
    if not role_data:
        return _err(request, "That role does not exist.", 404)
    text = role_data["jd"]["external_text"]
    style, flags, clarity = scan_job_ad(text)
    return TEMPLATES.TemplateResponse(request, "job_ad.html", {
        "slug": slug, "role": role_data, "clarity": clarity, "style": style, "ad_text": text,
        "hollow": [f for f in flags if f.pattern_id == "hollow_phrase"],
        "missing": [f for f in flags if f.pattern_id == "missing_specifics"], "nav": "roles"})


@app.get("/role/{slug}/integrity", response_class=HTMLResponse)
def integrity(request: Request, slug: str):
    run = Run(slug)
    if not run.load_role():
        return _err(request, "That role does not exist.", 404)
    cands = run.candidates()
    return TEMPLATES.TemplateResponse(request, "injection.html", {
        "slug": slug, "flagged": [c for c in cands if c.document.hidden],
        "clean": [c for c in cands if not c.document.hidden], "nav": "roles"})


# ---------------------------------------------------------------- a candidate


@app.get("/role/{slug}/c/{cid}", response_class=HTMLResponse)
def candidate(request: Request, slug: str, cid: str, internal: int = 1):
    run = Run(slug)
    c = run.candidate(cid)
    role_data = run.load_role()
    if not c or not role_data:
        return _err(request, "That candidate does not exist.", 404, f"/role/{slug}")
    cp3 = _cp3_for(slug, c)
    return TEMPLATES.TemplateResponse(request, "candidate.html", {
        "slug": slug, "c": c, "role": role_data,
        "reqs": {r["id"]: r for r in role_data["requirements"]},
        "use_internal": bool(internal), "cp3": cp3,
        "answers": AnswerStore(slug).load(cid), "response_label": _response_label(cp3),
        "candidate_link": f"/apply/{ConsentStore(slug).token_for(cid)}",
        "reasons": REASONS, "rejection": FeedbackStore(slug).get(cid), "nav": "roles",
        "stage": StageStore(slug).load(cid), "stages": STAGES})


@app.post("/role/{slug}/c/{cid}/pass")
def record_pass(slug: str, cid: str, reason: str = Form(...), note: str = Form(""),
                set_stage: str = Form("")):
    c = Run(slug).candidate(cid)
    FeedbackStore(slug).record(Rejection(candidate_id=cid, reason=reason, note=note,
                                         fit_score=c.fit.score if c else 0.0))
    if set_stage:
        StageStore(slug).set(cid, set_stage)
    return RedirectResponse(f"/role/{slug}/c/{cid}#feedback", status_code=303)


@app.post("/role/{slug}/c/{cid}/stage")
def set_stage(slug: str, cid: str, stage: str = Form(...), back: str = Form("")):
    StageStore(slug).set(cid, stage)
    return RedirectResponse(back or f"/role/{slug}/c/{cid}", status_code=303)


@app.get("/role/{slug}/compare", response_class=HTMLResponse)
def compare(request: Request, slug: str, ids: str = ""):
    """Two candidates side by side, requirement by requirement.

    The product's whole argument is that a flat CV from the right person beats a polished one
    from the wrong person, and until now there was no screen that let anyone see that happen.
    """
    run = Run(slug)
    role_data = run.load_role()
    if not role_data:
        return _err(request, "That role does not exist.", 404)
    wanted = [i for i in ids.split(",") if i][:2]
    picked = [c for c in (run.candidate(i) for i in wanted) if c]
    if len(picked) < 2:
        return _err(request, "Pick two candidates to compare.", 400, f"/role/{slug}")
    reqs = {r["id"]: r for r in role_data["requirements"]}
    matches = [{m.requirement_id: m for m in c.fit.matches} for c in picked]
    rows = []
    for rid, r in reqs.items():
        a, b = matches[0].get(rid), matches[1].get(rid)
        credit = {"strong": 1.0, "moderate": 0.6, "weak": 0.2, "missing": 0.0}
        rows.append({
            "req": r, "a": a, "b": b,
            "a_cov": credit.get(a.strength, 0) if a else 0,
            "b_cov": credit.get(b.strength, 0) if b else 0,
            "diverges": bool(a and b and a.strength != b.strength)})
    rows.sort(key=lambda x: (not x["diverges"], x["req"]["kind"] != "required"))
    return TEMPLATES.TemplateResponse(request, "compare.html", {
        "slug": slug, "role": role_data, "a": picked[0], "b": picked[1], "rows": rows,
        "nav": "roles"})


@app.get("/role/{slug}/c/{cid}/ask", response_class=HTMLResponse)
def ask_questions(request: Request, slug: str, cid: str):
    """What the recruiter sends, and what the candidate will see when they open it."""
    run = Run(slug)
    c = run.candidate(cid)
    role_data = run.load_role()
    if not c or not role_data:
        return _err(request, "That candidate does not exist.", 404, f"/role/{slug}")
    StageStore(slug).set(cid, "questions_sent")
    link = f"/apply/{ConsentStore(slug).token_for(cid)}"
    return TEMPLATES.TemplateResponse(request, "ask.html", {
        "slug": slug, "c": c, "role": role_data, "link": link, "nav": "roles",
        "message": (
            f"Hello,\n\nThank you for applying for {role_data['jd']['title']}. Before we take "
            f"this further there are a couple of things we would like to hear from you in your "
            f"own words.\n\nYou can answer them here — it should take a few minutes, and you "
            f"can also see exactly what we read from your CV:\n\n{{link}}\n\n"
            f"No decision has been made, and nothing is automated: a person reviews every "
            f"application.\n\nBest wishes")})


@app.post("/role/{slug}/c/{cid}/clear")
def clear_flags(slug: str, cid: str):
    """A human deciding the flags do not matter. Recorded, not deleted - a checkpoint that can
    be silently cleared is a checkpoint nobody can audit."""
    FeedbackStore(slug).record(Rejection(
        candidate_id=cid, reason="cleared_by_human", note="flags reviewed and cleared",
        fit_score=(Run(slug).candidate(cid).fit.score if Run(slug).candidate(cid) else 0.0)))
    return RedirectResponse(f"/role/{slug}/c/{cid}#review", status_code=303)


# ---------------------------------------------------------------- global views


@app.get("/market", response_class=HTMLResponse)
def market(request: Request):
    all_feedback = {"total": 0, "by_reason": [], "our_errors": 0, "contradicting": 0}
    for r in roles():
        s = FeedbackStore(r["slug"]).summary()
        all_feedback["total"] += s["total"]
        all_feedback["our_errors"] += s["our_errors"]
        all_feedback["contradicting"] += s["contradicting"]
        all_feedback["by_reason"] += s["by_reason"]
    return TEMPLATES.TemplateResponse(request, "market.html", {
        "stats": corpus_stats(), "clusters": duplicates(), "feedback": all_feedback,
        "nav": "market"})


# ---------------------------------------------------------------- candidate side


def _find_consent(token: str):
    for r in roles():
        c = ConsentStore(r["slug"]).by_token(token)
        if c:
            return r["slug"], c
    return None, None


@app.get("/apply/{token}", response_class=HTMLResponse)
def candidate_portal(request: Request, token: str):
    slug, consent = _find_consent(token)
    if not consent:
        return _err(request, "This application link is not valid.", 404)
    run = Run(slug)
    c = run.candidate(consent.candidate_id)
    role_data = run.load_role()
    if not c or not role_data:
        return _err(request, "This application could not be found.", 404)
    _, ad_flags, clarity = scan_job_ad(role_data["jd"]["external_text"])
    return TEMPLATES.TemplateResponse(request, "candidate_portal.html", {
        "c": c, "role": role_data, "consent": consent, "scopes": SCOPES,
        "reqs": {r["id"]: r for r in role_data["requirements"]},
        "answers": AnswerStore(slug).load(consent.candidate_id),
        "casual_question": CASUAL_QUESTION, "token": token, "clarity": clarity,
        "ad_missing": [f for f in ad_flags if f.pattern_id == "missing_specifics"]})


@app.post("/apply/{token}/consent")
def set_consent(token: str, scope: str = Form(...), granted: str = Form("")):
    slug, consent = _find_consent(token)
    if not consent:
        return RedirectResponse("/", status_code=303)
    revoked = consent.set(scope, granted == "on")
    ConsentStore(slug).save(consent)
    if revoked:
        # Withdrawal has to delete what was gathered under that scope, or it is not withdrawal.
        from ..config import CACHE_DIR

        for f in CACHE_DIR.glob("gh_*.json" if scope == "github" else "oa_*.json"):
            f.unlink(missing_ok=True)
        run = Run(slug)
        c = run.candidate(consent.candidate_id)
        if c:
            c.verifications = [v for v in c.verifications if v.source_scope != scope]
            c.consent_grants = dict(consent.grants)
            c.consent_summary = consent.summary()
            run.save_candidate(c)
    return RedirectResponse(f"/apply/{token}#data", status_code=303)


@app.post("/apply/{token}/answers")
async def submit_answers(request: Request, token: str):
    slug, consent = _find_consent(token)
    if not consent:
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    c = Run(slug).candidate(consent.candidate_id)
    questions = [q["question"] for q in (c.questions if c else [])]
    AnswerStore(slug).record(
        consent.candidate_id, questions,
        [str(form.get(f"a{i}", "")) for i in range(len(questions))],
        str(form.get("baseline", "")))
    return RedirectResponse(f"/apply/{token}#answers", status_code=303)
