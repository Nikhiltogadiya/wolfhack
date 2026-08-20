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


class Run:
    def __init__(self, name: str = "demo"):
        self.dir = RUNS / name
        self.dir.mkdir(parents=True, exist_ok=True)

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
