"""Persist assembled results as JSON on disk.

No database. A run is a directory of JSON files, which means the demo state is inspectable,
diffable, committable, and trivially reset - all of which matter more in a 24-hour build than
anything a schema would buy us.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR
from .jd.model import JobDescription
from .schemas import CandidateResult, Requirement

RUNS = DATA_DIR / "runs"


def slugify(text: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", (text or "role").lower()).strip("-")[:48]
    return slug or "role"


def roles() -> list[dict]:
    """Every role that exists, newest first.

    A role is a directory. There is no index file to fall out of sync with the directories it
    describes - the filesystem is the index.
    """
    out = []
    if not RUNS.exists():
        return out
    for d in RUNS.iterdir():
        if not d.is_dir():
            continue
        run = Run(d.name)
        role = run.load_role()
        if not role:
            continue
        cands = run.candidates()
        flagged = sum(1 for c in cands if c.cp2.verdict.value == "flag_for_human")
        out.append({
            "slug": d.name,
            "title": role["jd"].get("title") or d.name,
            "candidates": len(cands),
            "flagged": flagged,
            "awaiting": sum(1 for c in cands if c.fit.dealbreakers_unstated),
            "top_fit": max((c.fit.score for c in cands), default=0.0),
            "mean_fit": (sum(c.fit.score for c in cands) / len(cands)) if cands else 0.0,
            "requirements": len(role.get("requirements", [])),
            "internal": sum(1 for r in role.get("requirements", []) if r.get("source") == "internal"),
            "blocked": sum(1 for e in role["jd"].get("audit", []) if e["event"] == "internal_constraint_REFUSED"),
            "clarity": role.get("clarity", 0.0),
            "modified": d.stat().st_mtime,
        })
    return sorted(out, key=lambda r: -r["modified"])


class Run:
    def __init__(self, name: str = "demo"):
        self.name = name
        self.dir = RUNS / name
        self.dir.mkdir(parents=True, exist_ok=True)

    @property
    def exists(self) -> bool:
        return (self.dir / "role.json").exists()

    def delete_candidate(self, cid: str) -> None:
        (self.dir / f"c_{cid}.json").unlink(missing_ok=True)

    # ---- role ----
    def save_role(self, jd: JobDescription, requirements: list[Requirement], clarity: float = 0.0,
                  ad_flags: list | None = None) -> None:
        (self.dir / "role.json").write_text(json.dumps({
            "jd": jd.model_dump(),
            "requirements": [r.model_dump() for r in requirements],
            "clarity": clarity,
            "ad_flags": [f.model_dump() if hasattr(f, "model_dump") else f for f in (ad_flags or [])],
        }, indent=2))

    def load_role(self) -> dict | None:
        f = self.dir / "role.json"
        return json.loads(f.read_text()) if f.exists() else None

    # ---- candidates ----
    def save_candidate(self, result: CandidateResult) -> None:
        (self.dir / f"c_{result.candidate_id}.json").write_text(result.model_dump_json(indent=2))

    def candidates(self) -> list[CandidateResult]:
        out = [CandidateResult.model_validate_json(f.read_text())
               for f in sorted(self.dir.glob("c_*.json"))]
        return sorted(out, key=lambda c: -c.fit.score)

    def candidate(self, cid: str) -> CandidateResult | None:
        f = self.dir / f"c_{cid}.json"
        return CandidateResult.model_validate_json(f.read_text()) if f.exists() else None
