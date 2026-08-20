"""The recruiter dashboard.

One FastAPI process serving server-rendered Jinja - no npm, no build step, no API layer to keep
in sync with a client. The three screens are the ones the demo actually walks.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..candidate.answers import AnswerStore
from ..candidate.consent import SCOPES, ConsentStore
from ..jd.slop import scan_job_ad
from ..slop.response import CASUAL_QUESTION, scan_responses
from ..store import Run

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="Fit Happens")


@app.get("/", response_class=HTMLResponse)
def ranking(request: Request, internal: int = 1):
    run = Run()
    role = run.load_role()
    if not role:
        return HTMLResponse("<p style='font-family:sans-serif;padding:3rem'>"
                            "No run found. Build one with <code>uv run python scripts/build_demo.py</code>.</p>")
    candidates = [c for c in run.candidates()]
    cp3s = {c.candidate_id: _cp3_for(c) for c in candidates}
    response_labels = {cid: _response_label(v) for cid, v in cp3s.items()}
    reqs = role["requirements"]
    if not internal:
        # The reveal: re-rank on the public advert alone by dropping the internal requirements
        # from every candidate's coverage. Recomputed, never a second stored score.
        from ..fit.score import score_fit
        from ..schemas import Requirement

        public = [Requirement(**r) for r in reqs if r["source"] == "external"]
        ids = {r.id for r in public}
        for c in candidates:
            c.fit = score_fit([m for m in c.fit.matches if m.requirement_id in ids], public)
        candidates.sort(key=lambda c: -c.fit.score)
    return TEMPLATES.TemplateResponse(request, "ranking.html", {
         "role": role, "candidates": candidates,
        "use_internal": bool(internal),
        "required_count": sum(1 for r in reqs if r["kind"] == "required"),
        "preferred_count": sum(1 for r in reqs if r["kind"] == "preferred"),
        "internal_count": sum(1 for r in reqs if r["source"] == "internal"),
        "blocked": sum(1 for e in role["jd"].get("audit", []) if e["event"] == "internal_constraint_REFUSED"),
        "response_labels": response_labels,
    })


@app.get("/candidate/{cid}", response_class=HTMLResponse)
def candidate(request: Request, cid: str, internal: int = 1):
    run = Run()
    c = run.candidate(cid)
    if not c:
        return HTMLResponse("<p style='font-family:sans-serif;padding:3rem'>Unknown candidate.</p>", 404)
    role = run.load_role()
    reqs = {r["id"]: r for r in role["requirements"]}
    cp3 = _cp3_for(c)
    return TEMPLATES.TemplateResponse(request, "candidate.html", {
        "c": c, "role": role, "reqs": reqs,
        "use_internal": bool(internal),
        "cp3": cp3,
        "answers": AnswerStore().load(cid),
        "response_label": _response_label(cp3),
        "candidate_link": f"/apply/{ConsentStore().token_for(cid)}",
    })


@app.get("/injection", response_class=HTMLResponse)
def injection(request: Request):
    run = Run()
    flagged = [c for c in run.candidates() if c.document.hidden]
    clean = [c for c in run.candidates() if not c.document.hidden]
    return TEMPLATES.TemplateResponse(request, "injection.html", {
         "flagged": flagged, "clean": clean})


@app.get("/job-ad", response_class=HTMLResponse)
def job_ad(request: Request):
    run = Run()
    role = run.load_role()
    text = role["jd"]["external_text"] if role else ""
    style, flags, clarity = scan_job_ad(text)
    return TEMPLATES.TemplateResponse(request, "job_ad.html", {
         "role": role, "clarity": clarity,
        "hollow": [f for f in flags if f.pattern_id == "hollow_phrase"],
        "missing": [f for f in flags if f.pattern_id == "missing_specifics"],
        "style": style})


# ---------------------------------------------------------------- candidate side
#
# A tokenised link, no account. A candidate who has just applied should not have to create
# credentials with the company that has not hired them yet.


def _cp3_for(c) -> object | None:
    """Checkpoint 3, computed at render time.

    Deliberately not stored on the candidate record: answers arrive long after the pipeline
    ran, and a stored copy would go stale the moment someone edits a response. The scan is
    pure and cheap, so recomputing is simpler than invalidating.
    """
    answers = AnswerStore().load(c.candidate_id)
    if not answers.submitted:
        return None
    return scan_responses(answers.answers, c.claims, c.employment)


def _response_label(cp3) -> tuple[str, str]:
    if cp3 is None:
        return "PENDING", "grey"
    n = len([f for f in cp3.flags if f.pattern_id not in {
        "stock_phrases", "self_significance", "negative_parallelism", "copula_avoidance",
        "uniform_rhythm", "rule_of_three", "em_dash_density", "style_divergence"}])
    if cp3.verdict.value == "flag_for_human":
        return (f"{n} FLAG" if n == 1 else f"{n} FLAGS"), "red"
    if cp3.verdict.value == "inconclusive":
        return "NOT CORROBORATED", "amber"
    return "LOW RISK", "green"


def _candidate_context(cid: str):
    run, consent_store, answer_store = Run(), ConsentStore(), AnswerStore()
    c = run.candidate(cid)
    if not c:
        return None
    role = run.load_role()
    reqs = {r["id"]: r for r in role["requirements"]} if role else {}
    consent = consent_store.load(cid)
    answers = answer_store.load(cid)

    cp3 = None
    if answers.submitted:
        cp3 = scan_responses(answers.answers, c.claims, c.employment)

    return {
        "c": c, "role": role, "reqs": reqs, "consent": consent, "scopes": SCOPES,
        "answers": answers, "cp3": cp3, "casual_question": CASUAL_QUESTION,
        "token": consent_store.token_for(cid),
    }


@app.get("/apply/{token}", response_class=HTMLResponse)
def candidate_portal(request: Request, token: str):
    consent = ConsentStore().by_token(token)
    if not consent:
        return HTMLResponse("<p style='font-family:sans-serif;padding:3rem'>"
                            "This link is not valid.</p>", 404)
    ctx = _candidate_context(consent.candidate_id)
    if not ctx:
        return HTMLResponse("<p style='font-family:sans-serif;padding:3rem'>"
                            "Application not found.</p>", 404)
    _, ad_flags, clarity = scan_job_ad(ctx["role"]["jd"]["external_text"]) if ctx["role"] else (None, [], 0)
    ctx |= {"request": request, "clarity": clarity,
            "ad_missing": [f for f in ad_flags if f.pattern_id == "missing_specifics"]}
    return TEMPLATES.TemplateResponse(request, "candidate_portal.html", ctx)


@app.post("/apply/{token}/consent")
def set_consent(token: str, scope: str = Form(...), granted: str = Form("")):
    store = ConsentStore()
    consent = store.by_token(token)
    if not consent:
        return RedirectResponse(f"/apply/{token}", status_code=303)
    revoked = consent.set(scope, granted == "on")
    store.save(consent)
    if revoked:
        # Withdrawing consent has to delete what was gathered under it, or it is not consent.
        # The cached artefact is removed and the candidate's record rebuilt without it.
        from ..config import CACHE_DIR

        for f in CACHE_DIR.glob("gh_*.json" if scope == "github" else "oa_*.json"):
            f.unlink(missing_ok=True)
        run = Run()
        c = run.candidate(consent.candidate_id)
        if c:
            c.verifications = [v for v in c.verifications if v.source_scope != scope]
            c.consent_grants = dict(consent.grants)
            c.consent_summary = consent.summary()
            run.save_candidate(c)
    return RedirectResponse(f"/apply/{token}#data", status_code=303)


@app.post("/apply/{token}/answers")
async def submit_answers(request: Request, token: str):
    consent = ConsentStore().by_token(token)
    if not consent:
        return RedirectResponse(f"/apply/{token}", status_code=303)
    form = await request.form()
    cid = consent.candidate_id
    c = Run().candidate(cid)
    questions = [q["question"] for q in (c.questions if c else [])]
    texts = [str(form.get(f"a{i}", "")) for i in range(len(questions))]
    AnswerStore().record(cid, questions, texts, str(form.get("baseline", "")))
    return RedirectResponse(f"/apply/{token}#answers", status_code=303)
