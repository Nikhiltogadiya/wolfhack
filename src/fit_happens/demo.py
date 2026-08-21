"""One-click demo seeding.

The old empty state told a first-time visitor to run a shell command. That is not an empty
state, it is a dead end - and the first thing a judge would have seen. This builds the same
run `scripts/build_demo.py` builds, from inside the app.

Runs against the cache, so with a warm cache it takes seconds and needs no network.
"""

from __future__ import annotations

import glob
import shutil
from pathlib import Path

from .candidate.consent import ConsentStore
from .jd.model import InternalConstraint, JobDescription
from .jd.parse import parse_jd
from .jd.slop import scan_job_ad
from .pipeline import run_candidate
from .store import Run

SLUG = "demo"
JD_PATH = Path("data/demo/jd_external.md")
RESUMES = "data/demo/resumes/*.pdf"

# Real operational constraints, plus one that must be refused. The refusal is part of the demo:
# the guard is only credible if you watch it reject something.
INTERNAL = [
    InternalConstraint(
        field_name="team_context",
        value=("we go into an ISO 27001 audit next year, so this hire must have worked under a "
               "formal compliance or accreditation regime"),
        required=True, weight=1.5),
    InternalConstraint(field_name="mentoring_capacity",
                       value="the team is junior, this hire must mentor two engineers", required=True),
    InternalConstraint(field_name="onsite_days", value="three days a week in the Berlin office"),
    InternalConstraint(field_name="team_context",
                       value="we want a young energetic team with no career gaps"),
]


def seed(slug: str = SLUG) -> dict:
    if not JD_PATH.exists():
        return {"ok": False, "error": "demo job description is missing"}

    text = JD_PATH.read_text()
    title, external = parse_jd(text)
    jd = JobDescription(title=title, external_text=text, internal=INTERNAL)
    reqs = external + jd.internal_requirements()
    _, ad_flags, clarity = scan_job_ad(text)

    run = Run(slug)
    run.save_role(jd, reqs, clarity, ad_flags)

    built = 0
    for path in sorted(glob.glob(RESUMES)):
        cid = Path(path).stem
        consent = ConsentStore(slug).load(cid)
        result = run_candidate(path, jd, reqs, consent)
        run.save_candidate(result)
        ConsentStore(slug).save(consent)
        built += 1
    return {"ok": True, "candidates": built, "blocked": jd.blocked_count()}


def ensure_demo_resumes() -> int:
    """Copy the demo CVs into place if the corpus is available but they are not."""
    dest = Path("data/demo/resumes")
    if list(dest.glob("*.pdf")):
        return len(list(dest.glob("*.pdf")))
    dest.mkdir(parents=True, exist_ok=True)
    for rid, name in (("17641670", "priya_raman"), ("10704573", "daniel_kowalski"),
                      ("19796840", "amara_osei")):
        hit = glob.glob(f"data/corpus/data/data/*/{rid}.pdf")
        if hit:
            shutil.copy(hit[0], dest / f"{name}.pdf")
    return len(list(dest.glob("*.pdf")))
