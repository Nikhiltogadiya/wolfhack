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
def new_role_form(request: Request):
    return TEMPLATES.TemplateResponse(request, "role_new.html", {
        "allowed": ALLOWED_FIELDS, "nav": "roles", "checked": None})


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
    form = await request.form()
    title = str(form.get("title", "")).strip()
    jd_text = str(form.get("jd_text", "")).strip()
    if not jd_text:
        return _err(request, "A role needs a job description to score against.", 400, "/roles/new")

    slug = slugify(title or "role")
    base, n = slug, 2
    while Run(slug).exists:
        slug, n = f"{base}-{n}", n + 1

    from ..jd.model import InternalConstraint, JobDescription
    from ..jd.parse import parse_jd

    internal = []
    for i in range(6):
        f, v = str(form.get(f"if{i}", "")), str(form.get(f"iv{i}", "")).strip()
        if f and v:
            internal.append(InternalConstraint(field_name=f, value=v,
                                               required=bool(form.get(f"ir{i}"))))
    parsed_title, external = parse_jd(jd_text, title)
    jd = JobDescription(title=title or parsed_title, external_text=jd_text, internal=internal)
    reqs = external + jd.internal_requirements()
    _, ad_flags, clarity = scan_job_ad(jd_text)
    Run(slug).save_role(jd, reqs, clarity, ad_flags)
    return RedirectResponse(f"/role/{slug}", status_code=303)


@app.get("/role/{slug}", response_class=HTMLResponse)
def role(request: Request, slug: str, internal: int = 1):
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

    return TEMPLATES.TemplateResponse(request, "ranking.html", {
        "slug": slug, "role": role_data, "candidates": candidates,
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
        "reasons": REASONS, "rejection": FeedbackStore(slug).get(cid), "nav": "roles"})


@app.post("/role/{slug}/c/{cid}/pass")
def record_pass(slug: str, cid: str, reason: str = Form(...), note: str = Form("")):
    c = Run(slug).candidate(cid)
    FeedbackStore(slug).record(Rejection(candidate_id=cid, reason=reason, note=note,
                                         fit_score=c.fit.score if c else 0.0))
    return RedirectResponse(f"/role/{slug}/c/{cid}#feedback", status_code=303)


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
