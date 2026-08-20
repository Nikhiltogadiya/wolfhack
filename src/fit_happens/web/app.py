"""The recruiter dashboard.

One FastAPI process serving server-rendered Jinja - no npm, no build step, no API layer to keep
in sync with a client. The three screens are the ones the demo actually walks.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..jd.slop import scan_job_ad
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
    })


@app.get("/candidate/{cid}", response_class=HTMLResponse)
def candidate(request: Request, cid: str, internal: int = 1):
    run = Run()
    c = run.candidate(cid)
    if not c:
        return HTMLResponse("<p style='font-family:sans-serif;padding:3rem'>Unknown candidate.</p>", 404)
    role = run.load_role()
    reqs = {r["id"]: r for r in role["requirements"]}
    return TEMPLATES.TemplateResponse(request, "candidate.html", {
         "c": c, "role": role, "reqs": reqs,
        "use_internal": bool(internal),
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
