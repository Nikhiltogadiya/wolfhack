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
from ..candidate.applications import (
    Application, ApplicationStore, candidate_id_for, find_by_email, looks_like_email)
from ..candidate.consent import SCOPES, ConsentStore
from ..feedback import REASONS, FeedbackStore, Rejection
from ..jd.discovery import corpus_stats, duplicates
from ..jd.guard import ALLOWED_FIELDS, check_value
from ..jd.slop import scan_job_ad
from ..slop.response import CASUAL_QUESTION, scan_responses
from ..stages import ORDER as STAGE_ORDER, STAGES, StageStore
from ..store import Run, roles, slugify
from . import auth, tasks  # noqa: E402

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
# Available to every template, so the hiring pages can say when they are unprotected.
TEMPLATES.env.globals["gated"] = auth.configured  # callable: templates use {% if gated() %}
app = FastAPI(title="Fit Happens")


# Eight /hiring routes shipped with no gate - upload, seed, set-stage, record-pass,
# clear-flags, dismiss-notices, status, check-internal - and they were exactly the eight
# written without a `request` parameter, so `auth.require` was impossible to call and got
# quietly dropped. Gating them one by one would just wait for the ninth. The prefix is the
# boundary, so the prefix is where the check goes.
_OPEN_HIRING_PATHS = {"/hiring/sign-in", "/hiring/sign-out"}


@app.middleware("http")
async def _gate_hiring(request: Request, call_next):
    path = request.url.path
    gated = path.startswith("/hiring") and path not in _OPEN_HIRING_PATHS
    if gated and (gate := auth.require(request)) is not None:
        return gate
    return await call_next(request)

UPLOADS = Path("data/uploads")
STYLE_PATTERNS = {"stock_phrases", "self_significance", "negative_parallelism", "copula_avoidance",
                  "uniform_rhythm", "rule_of_three", "em_dash_density", "style_divergence"}


def _err(request: Request, message: str, status: int = 404, back: str = "/") -> HTMLResponse:
    """Public callers get the public shell. error.html extends base.html, so a candidate with
    a dead application link was being shown the hiring sidebar - and, with no passcode set,
    the "this area is unprotected" banner meant for the recruiter."""
    # Decided from the path being served, not from `back`: most call sites leave `back` at
    # its default, and a recruiter 404 was landing on the public shell because of it.
    template = "error.html" if request.url.path.startswith("/hiring") else "error_public.html"
    return TEMPLATES.TemplateResponse(request, template,
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


@app.get("/hiring", response_class=HTMLResponse)
def overview(request: Request):
    if (gate := auth.require(request)):
        return gate
    all_roles = roles()
    everyone = [(r, c) for r in all_roles for c in Run(r["slug"]).candidates()]
    stage_of, replied_count = {}, 0
    for r in all_roles:
        st, ans = StageStore(r["slug"]), AnswerStore(r["slug"])
        for c in Run(r["slug"]).candidates():
            rec = st.load(c.candidate_id)
            stage_of[(r["slug"], c.candidate_id)] = rec
            if ans.load(c.candidate_id).submitted and rec.stage == "questions_sent":
                replied_count += 1
    return TEMPLATES.TemplateResponse(request, "overview.html", {
        "stage_of": stage_of, "replied_count": replied_count,
        "roles": all_roles,
        "open_roles": len(all_roles),
        "applicants": sum(r["candidates"] for r in all_roles),
        "needs_review": sum(r["flagged"] for r in all_roles),
        "mean_fit": (sum(c.fit.score for _, c in everyone) / len(everyone)) if everyone else 0.0,
        "top": sorted(everyone, key=lambda rc: -rc[1].fit.score)[:6],
        "nav": "overview",
    })


@app.post("/hiring/seed")
def seed_demo(background: BackgroundTasks):
    """One click to a populated demo. The old empty state told a first-time visitor to go and
    run a shell command, which is not an empty state, it is a dead end."""
    from ..demo import seed

    background.add_task(seed)
    return RedirectResponse("/hiring?seeding=1", status_code=303)


# ---------------------------------------------------------------- a role


@app.get("/hiring/roles", response_class=HTMLResponse)
def roles_list(request: Request):
    """A list of roles. The nav used to jump straight to 'create new', which is not a list."""
    if (gate := auth.require(request)):
        return gate
    return TEMPLATES.TemplateResponse(request, "roles_list.html", {
        "roles": roles(), "nav": "roles"})


@app.get("/hiring/role/{slug}/edit", response_class=HTMLResponse)
def edit_role_form(request: Request, slug: str):
    if (gate := auth.require(request)):
        return gate
    role_data = Run(slug).load_role()
    if not role_data:
        return _err(request, "That role does not exist.", 404, "/hiring/roles")
    return TEMPLATES.TemplateResponse(request, "role_edit.html", {
        "slug": slug, "role": role_data, "allowed": ALLOWED_FIELDS, "nav": "roles",
        "internal": role_data["jd"].get("internal", [])})


@app.post("/hiring/role/{slug}/edit")
async def edit_role(request: Request, slug: str):
    """Re-parse the advert and rebuild the requirements.

    Existing candidates keep their stored scores until they are re-run - shown on the page,
    because silently leaving stale scores against changed requirements would be worse than
    saying so.
    """
    if (gate := auth.require(request)):
        return gate
    run = Run(slug)
    role_data = run.load_role()
    if not role_data:
        return _err(request, "That role does not exist.", 404, "/hiring/roles")

    form = await request.form()
    from ..jd.model import InternalConstraint, JobDescription
    from ..jd.parse import parse_jd

    jd_text = str(form.get("jd_text", "")).strip() or role_data["jd"]["external_text"]
    title = str(form.get("title", "")).strip() or role_data["jd"]["title"]
    internal = [
        InternalConstraint(field_name=str(form.get(f"if{i}")), value=str(form.get(f"iv{i}")).strip(),
                           required=bool(form.get(f"ir{i}")))
        for i in range(8)
        if str(form.get(f"if{i}", "")) and str(form.get(f"iv{i}", "")).strip()
    ]
    parsed_title, external = parse_jd(jd_text, title)
    jd = JobDescription(title=title or parsed_title, external_text=jd_text, internal=internal)
    reqs = external + jd.internal_requirements()
    _, ad_flags, clarity = scan_job_ad(jd_text)
    run.save_role(jd, reqs, clarity, ad_flags)
    return RedirectResponse(f"/hiring/role/{slug}?edited=1", status_code=303)


@app.post("/hiring/role/{slug}/close")
def close_role(request: Request, slug: str, closed: str = Form("")):
    if (gate := auth.require(request)):
        return gate
    Run(slug).set_closed(closed == "on")
    return RedirectResponse(f"/hiring/role/{slug}", status_code=303)


@app.post("/hiring/role/{slug}/c/{cid}/remove")
def remove_candidate(request: Request, slug: str, cid: str):
    """Duplicate application, wrong file attached. Was permanent until now."""
    if (gate := auth.require(request)):
        return gate
    Run(slug).delete_candidate(cid)
    return RedirectResponse(f"/hiring/role/{slug}", status_code=303)


@app.post("/hiring/role/{slug}/bulk")
async def bulk_stage(request: Request, slug: str):
    """Shortlisting five people used to be five page loads."""
    if (gate := auth.require(request)):
        return gate
    form = await request.form()
    stage = str(form.get("stage", ""))
    ids = form.getlist("ids")
    store = StageStore(slug)
    for cid in ids:
        store.set(str(cid), stage)
    return RedirectResponse(f"/hiring/role/{slug}", status_code=303)


@app.get("/hiring/roles/new", response_class=HTMLResponse)
def new_role_step1(request: Request):
    if (gate := auth.require(request)):
        return gate
    """Step 1 of 3. Just the advert - asking for everything at once was the problem."""
    return TEMPLATES.TemplateResponse(request, "role_step1.html", {"nav": "roles", "step": 1})


@app.post("/hiring/roles/preview", response_class=HTMLResponse)
async def new_role_step2(request: Request):
    if (gate := auth.require(request)):
        return gate
    """Step 2 of 3. Show her what we extracted BEFORE the role exists.

    Previously she pasted an advert and pressed Create having seen nothing of what we
    understood; the first time she learned what we read was after the fact. Requirements are
    editable here, because our parse is a draft of her intent, not a ruling on it.
    """
    form = await request.form()
    jd_text = str(form.get("jd_text", "")).strip()
    title = str(form.get("title", "")).strip()
    if not jd_text:
        return _err(request, "Paste the advert first - we score against it.", 400, "/hiring/roles/new")

    from ..jd.parse import parse_jd

    parsed_title, reqs = parse_jd(jd_text, title)
    _, ad_flags, clarity = scan_job_ad(jd_text)
    return TEMPLATES.TemplateResponse(request, "role_step2.html", {
        "nav": "roles", "step": 2, "title": title or parsed_title, "jd_text": jd_text,
        "requirements": reqs, "clarity": clarity, "allowed": ALLOWED_FIELDS,
        "missing": [f for f in ad_flags if f.pattern_id == "missing_specifics"],
        "hollow": [f for f in ad_flags if f.pattern_id == "hollow_phrase"]})


@app.post("/hiring/roles/check")
def check_internal(field_name: str = Form(...), value: str = Form("")):
    """Live guard feedback while the recruiter types an internal criterion.

    Refusing at submit time would be too late to teach anything. Refusing as they type is where
    the compliance story stops being a slide and becomes something they experience.
    """
    r = check_value(field_name, value)
    return JSONResponse({"allowed": r.allowed, "reason": r.reason})


@app.post("/hiring/roles/new")
async def create_role(request: Request, background: BackgroundTasks):
    if (gate := auth.require(request)):
        return gate
    """Step 3: create the role, honouring the requirement edits, and start any CVs processing."""
    form = await request.form()
    title = str(form.get("title", "")).strip()
    jd_text = str(form.get("jd_text", "")).strip()
    if not jd_text:
        return _err(request, "A role needs an advert to score against.", 400, "/hiring/roles/new")

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

    return RedirectResponse(f"/hiring/role/{slug}", status_code=303)


@app.get("/hiring/role/{slug}", response_class=HTMLResponse)
def role(request: Request, slug: str, internal: int = 1, sort: str = "fit",
         filter_by: str = ""):
    if (gate := auth.require(request)):
        return gate
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
    answers_store = AnswerStore(slug)
    # She asked, they replied, and she has not moved them on. Without this she has to keep
    # revisiting the page to find out whether anyone answered.
    replied = {c.candidate_id for c in candidates
               if answers_store.load(c.candidate_id).submitted
               and stage_of[c.candidate_id].stage == "questions_sent"}
    if filter_by == "replied":
        candidates = [c for c in candidates if c.candidate_id in replied]
    elif filter_by == "review":
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
        "replied": replied, "closed": run.closed, "edited": bool(request.query_params.get("edited")),
        "total": len(run.candidates()),
        "use_internal": bool(internal),
        "required_count": sum(1 for r in reqs if r["kind"] == "required"),
        "preferred_count": sum(1 for r in reqs if r["kind"] == "preferred"),
        "internal_count": sum(1 for r in reqs if r["source"] == "internal"),
        "blocked": sum(1 for e in role_data["jd"].get("audit", []) if e["event"] == "internal_constraint_REFUSED"),
        "response_labels": {cid: _response_label(v) for cid, v in cp3s.items()},
        "pending": tasks.pending(slug), "recent": tasks.recent(slug), "nav": "roles",
    })


@app.post("/hiring/role/{slug}/upload")
async def upload_cvs(slug: str, background: BackgroundTasks, files: list[UploadFile] = None):
    run = Run(slug)
    if not run.exists:
        return RedirectResponse("/hiring", status_code=303)
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
    return RedirectResponse(f"/hiring/role/{slug}", status_code=303)


@app.post("/hiring/role/{slug}/dismiss")
def dismiss_notices(slug: str):
    """Clear finished and failed upload notices. Without this a single old failure sat at the
    top of the page permanently, describing a problem that had already been resolved."""
    tasks.clear_finished(slug)
    return RedirectResponse(f"/hiring/role/{slug}", status_code=303)


@app.get("/hiring/role/{slug}/status")
def role_status(slug: str):
    """Polled by the ranking page while uploads process."""
    return JSONResponse({"pending": tasks.pending(slug), "recent": tasks.recent(slug)})


@app.get("/hiring/role/{slug}/job-ad", response_class=HTMLResponse)
def job_ad(request: Request, slug: str):
    if (gate := auth.require(request)):
        return gate
    role_data = Run(slug).load_role()
    if not role_data:
        return _err(request, "That role does not exist.", 404)
    text = role_data["jd"]["external_text"]
    style, flags, clarity = scan_job_ad(text)
    return TEMPLATES.TemplateResponse(request, "job_ad.html", {
        "slug": slug, "role": role_data, "clarity": clarity, "style": style, "ad_text": text,
        "hollow": [f for f in flags if f.pattern_id == "hollow_phrase"],
        "missing": [f for f in flags if f.pattern_id == "missing_specifics"], "nav": "roles"})


@app.get("/hiring/role/{slug}/integrity", response_class=HTMLResponse)
def integrity(request: Request, slug: str):
    if (gate := auth.require(request)):
        return gate
    run = Run(slug)
    if not run.load_role():
        return _err(request, "That role does not exist.", 404)
    cands = run.candidates()
    return TEMPLATES.TemplateResponse(request, "injection.html", {
        "slug": slug, "flagged": [c for c in cands if c.document.hidden],
        "clean": [c for c in cands if not c.document.hidden], "nav": "roles"})


# ---------------------------------------------------------------- a candidate


@app.get("/hiring/role/{slug}/c/{cid}", response_class=HTMLResponse)
def candidate(request: Request, slug: str, cid: str, internal: int = 1):
    if (gate := auth.require(request)):
        return gate
    run = Run(slug)
    c = run.candidate(cid)
    role_data = run.load_role()
    if not c or not role_data:
        return _err(request, "That candidate does not exist.", 404, f"/hiring/role/{slug}")
    cp3 = _cp3_for(slug, c)
    return TEMPLATES.TemplateResponse(request, "candidate.html", {
        "slug": slug, "c": c, "role": role_data,
        "reqs": {r["id"]: r for r in role_data["requirements"]},
        "use_internal": bool(internal), "cp3": cp3,
        "answers": AnswerStore(slug).load(cid), "response_label": _response_label(cp3),
        "candidate_link": f"/apply/{ConsentStore(slug).token_for(cid)}",
        "reasons": REASONS, "rejection": FeedbackStore(slug).get(cid), "nav": "roles",
        "stage": StageStore(slug).load(cid), "stages": STAGES})


@app.post("/hiring/role/{slug}/c/{cid}/pass")
def record_pass(slug: str, cid: str, reason: str = Form(...), note: str = Form(""),
                set_stage: str = Form("")):
    c = Run(slug).candidate(cid)
    FeedbackStore(slug).record(Rejection(candidate_id=cid, reason=reason, note=note,
                                         fit_score=c.fit.score if c else 0.0))
    if set_stage:
        StageStore(slug).set(cid, set_stage)
    return RedirectResponse(f"/hiring/role/{slug}/c/{cid}#feedback", status_code=303)


@app.post("/hiring/role/{slug}/c/{cid}/stage")
def set_stage(slug: str, cid: str, stage: str = Form(...), back: str = Form("")):
    StageStore(slug).set(cid, stage)
    return RedirectResponse(back or f"/hiring/role/{slug}/c/{cid}", status_code=303)


@app.get("/hiring/role/{slug}/compare", response_class=HTMLResponse)
def compare(request: Request, slug: str, ids: str = ""):
    if (gate := auth.require(request)):
        return gate
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
        return _err(request, "Pick two candidates to compare.", 400, f"/hiring/role/{slug}")
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


@app.get("/hiring/role/{slug}/c/{cid}/ask", response_class=HTMLResponse)
def ask_questions(request: Request, slug: str, cid: str):
    if (gate := auth.require(request)):
        return gate
    """What the recruiter sends, and what the candidate will see when they open it."""
    run = Run(slug)
    c = run.candidate(cid)
    role_data = run.load_role()
    if not c or not role_data:
        return _err(request, "That candidate does not exist.", 404, f"/hiring/role/{slug}")
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


@app.post("/hiring/role/{slug}/c/{cid}/clear")
def clear_flags(slug: str, cid: str):
    """A human deciding the flags do not matter. Recorded, not deleted - a checkpoint that can
    be silently cleared is a checkpoint nobody can audit."""
    FeedbackStore(slug).record(Rejection(
        candidate_id=cid, reason="cleared_by_human", note="flags reviewed and cleared",
        fit_score=(Run(slug).candidate(cid).fit.score if Run(slug).candidate(cid) else 0.0)))
    return RedirectResponse(f"/hiring/role/{slug}/c/{cid}#review", status_code=303)


# ---------------------------------------------------------------- global views


@app.get("/hiring/market", response_class=HTMLResponse)
def market(request: Request):
    if (gate := auth.require(request)):
        return gate
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
    if not role_data:
        return _err(request, "This application could not be found.", 404)

    if not c:
        # They have just applied and their CV is still being read. Landing them on a 404 at the
        # exact moment they are most anxious about whether it went through would be the worst
        # possible reply, so this is a real state with a real answer.
        appn = ApplicationStore(slug).get(consent.candidate_id)
        pend = [t for t in tasks.recent(slug) if t["name"].startswith(consent.candidate_id)]
        state = pend[0] if pend else None
        return TEMPLATES.TemplateResponse(request, "processing.html", {
            "role": role_data, "token": token, "name": appn.name if appn else "",
            "failed": bool(state and state["state"] == "failed"),
            "error": state["error"] if state else "",
        })
    _, ad_flags, clarity = scan_job_ad(role_data["jd"]["external_text"])
    return TEMPLATES.TemplateResponse(request, "candidate_portal.html", {
        "c": c, "role": role_data, "consent": consent, "scopes": SCOPES,
        "reqs": {r["id"]: r for r in role_data["requirements"]},
        "answers": AnswerStore(slug).load(consent.candidate_id),
        "casual_question": CASUAL_QUESTION, "token": token, "clarity": clarity,
        "ad_missing": [f for f in ad_flags if f.pattern_id == "missing_specifics"]})


@app.post("/apply/{token}/consent")
def set_consent(request: Request, background: BackgroundTasks, token: str,
                scope: str = Form(...), granted: str = Form("")):
    slug, consent = _find_consent(token)
    if not consent:
        return _err(request, "That link is not valid any more.", 404, "/")
    if scope not in SCOPES or SCOPES[scope]["locked"]:
        return _err(request, "That is not a scope you can change.", 400, f"/apply/{token}")
    revoked = consent.set(scope, granted == "on")
    ConsentStore(slug).save(consent)
    if not revoked:
        # Granting has to trigger the fetch it authorises, or the toggle is decorative.
        background.add_task(tasks.reverify, slug, consent.candidate_id)
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
        return _err(request, "That link is not valid any more.", 404, "/")
    form = await request.form()
    c = Run(slug).candidate(consent.candidate_id)
    questions = [q["question"] for q in (c.questions if c else [])]
    AnswerStore(slug).record(
        consent.candidate_id, questions,
        [str(form.get(f"a{i}", "")) for i in range(len(questions))],
        str(form.get("baseline", "")))
    return RedirectResponse(f"/apply/{token}#answers", status_code=303)


# ---------------------------------------------------------------- the front door
#
# `/` used to be the recruiter dashboard, so a candidate arriving at the site was looking at
# other applicants' names and fit scores. Two audiences, two doors, stated plainly - which also
# makes it obvious at a glance that this is a two-sided thing rather than an ATS.


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    all_roles = roles()
    return TEMPLATES.TemplateResponse(request, "landing.html", {
        "open_roles": sum(1 for r in all_roles if r["slug"]),
        "roles": all_roles[:3]})


@app.get("/jobs", response_class=HTMLResponse)
def job_board(request: Request, q: str = ""):
    listed = []
    for r in roles():
        if r.get("closed"):
            continue  # a closed role is not open for applications
        role_data = Run(r["slug"]).load_role()
        if not role_data:
            continue
        text = role_data["jd"]["external_text"]
        if q and q.lower() not in (r["title"] + " " + text).lower():
            continue
        _, flags, clarity = scan_job_ad(text)
        listed.append({**r, "clarity": clarity,
                       "missing": [f.description.replace("the advert never states", "").strip()
                                   for f in flags if f.pattern_id == "missing_specifics"]})
    return TEMPLATES.TemplateResponse(request, "jobs.html", {"jobs": listed, "q": q})


@app.get("/jobs/{slug}", response_class=HTMLResponse)
def job_detail(request: Request, slug: str):
    run = Run(slug)
    role_data = run.load_role()
    if not role_data or run.closed:
        return _err(request, "That job is no longer listed.", 404, "/jobs")
    text = role_data["jd"]["external_text"]
    _, flags, clarity = scan_job_ad(text)
    reqs = [r for r in role_data["requirements"] if r["source"] == "external"]
    return TEMPLATES.TemplateResponse(request, "job_detail.html", {
        "slug": slug, "role": role_data, "ad_text": text, "clarity": clarity,
        "required": [r for r in reqs if r["kind"] == "required"],
        "preferred": [r for r in reqs if r["kind"] == "preferred"],
        "missing": [f.description.replace("the advert never states", "").strip()
                    for f in flags if f.pattern_id == "missing_specifics"],
        "hollow": [f for f in flags if f.pattern_id == "hollow_phrase"]})


@app.get("/jobs/{slug}/apply", response_class=HTMLResponse)
def apply_form(request: Request, slug: str):
    run = Run(slug)
    role_data = run.load_role()
    if not role_data or run.closed:
        return _err(request, "That job is no longer listed.", 404, "/jobs")
    return TEMPLATES.TemplateResponse(request, "apply.html", {
        "slug": slug, "role": role_data, "error": ""})


@app.post("/jobs/{slug}/apply")
async def submit_application(request: Request, slug: str, background: BackgroundTasks):
    run = Run(slug)
    role_data = run.load_role()
    if not role_data or run.closed:
        return _err(request, "That job is no longer listed.", 404, "/jobs")

    form = await request.form()
    name = str(form.get("name", "")).strip()
    email = str(form.get("email", "")).strip()
    cv = form.get("cv")

    problem = ""
    if not name:
        problem = "We need a name to put on your application."
    elif not looks_like_email(email):
        problem = "That email address does not look right — we need it so you can find your application again."
    elif not getattr(cv, "filename", ""):
        problem = "Please attach your CV. PDF, DOCX or TXT."
    if problem:
        return TEMPLATES.TemplateResponse(request, "apply.html", {
            "slug": slug, "role": role_data, "error": problem,
            "name": name, "email": email}, status_code=400)

    cid = candidate_id_for(name, email)
    dest = UPLOADS / slug
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"{cid}{Path(cv.filename).suffix.lower()}"
    with target.open("wb") as out:
        shutil.copyfileobj(cv.file, out)

    ApplicationStore(slug).save(Application(
        candidate_id=cid, name=name, email=email, role_slug=slug, cv_filename=cv.filename))
    ConsentStore(slug).save(ConsentStore(slug).load(cid))

    background.add_task(tasks.process_cv, slug, str(target), tasks.start(slug, cid))
    return RedirectResponse(f"/apply/{ConsentStore(slug).token_for(cid)}", status_code=303)


@app.get("/track", response_class=HTMLResponse)
def track(request: Request, email: str = ""):
    found = []
    if email:
        for slug, appn in find_by_email(email):
            role_data = Run(slug).load_role()
            found.append({"slug": slug, "app": appn,
                          "title": role_data["jd"]["title"] if role_data else slug,
                          "token": ConsentStore(slug).token_for(appn.candidate_id)})
    return TEMPLATES.TemplateResponse(request, "track.html", {
        "email": email, "found": found, "searched": bool(email)})


# ---------------------------------------------------------------- hiring gate


def _safe_next(target: str) -> str:
    """`next` is attacker-controlled on a sign-in page and went straight into a redirect.
    "//evil.example" counts as off-site too - a browser reads it as protocol-relative."""
    if target.startswith("/") and not target.startswith("//"):
        return target
    return "/hiring"


@app.get("/hiring/sign-in", response_class=HTMLResponse)
def sign_in_form(request: Request, next: str = "/hiring"):
    next = _safe_next(next)
    if auth.is_signed_in(request):
        return RedirectResponse(next, status_code=303)
    return TEMPLATES.TemplateResponse(request, "sign_in.html", {"next": next, "error": ""})


@app.post("/hiring/sign-in")
def do_sign_in(request: Request, passcode: str = Form(""), next: str = Form("/hiring")):
    next = _safe_next(next)
    if not auth.check(passcode):
        return TEMPLATES.TemplateResponse(request, "sign_in.html", {
            "next": next, "error": "That passcode is not right."}, status_code=401)
    resp = RedirectResponse(next, status_code=303)
    auth.sign_in(resp)
    return resp


@app.post("/hiring/sign-out")
def do_sign_out():
    resp = RedirectResponse("/", status_code=303)
    auth.sign_out(resp)
    return resp
