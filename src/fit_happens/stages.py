"""Where a candidate is in the process.

The product previously modelled only rejection: a recruiter could pass on someone and nothing
else. Real pipelines move people forward, and a tool that can only record a "no" is a tool that
quietly frames every decision as one.

Stages are set by a person, never by the system. Nothing here reads a score. That is the same
rule as everywhere else - the software ranks and flags, a human decides - and here it is the
difference between a stage and an automated hiring decision.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .config import DATA_DIR

# Ordered as the process runs, so the UI can show progress without hard-coding an order.
STAGES: dict[str, dict[str, str]] = {
    "new": {"label": "New", "tone": "grey",
            "hint": "Nobody has looked at this application yet."},
    "reviewing": {"label": "Reviewing", "tone": "blue",
                  "hint": "Someone is reading the evidence."},
    "questions_sent": {"label": "Questions sent", "tone": "blue",
                       "hint": "Waiting on the candidate to reply."},
    "shortlisted": {"label": "Shortlisted", "tone": "green",
                    "hint": "Moving forward to interview."},
    "passed": {"label": "Passed", "tone": "grey",
               "hint": "Not progressing. The reason is recorded."},
}
ORDER = list(STAGES)


class StageRecord(BaseModel):
    candidate_id: str
    stage: str = "new"
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    history: list[dict] = Field(default_factory=list)

    @property
    def label(self) -> str:
        return STAGES.get(self.stage, STAGES["new"])["label"]

    @property
    def tone(self) -> str:
        return STAGES.get(self.stage, STAGES["new"])["tone"]

    @property
    def hint(self) -> str:
        return STAGES.get(self.stage, STAGES["new"])["hint"]

    @property
    def is_decided(self) -> bool:
        return self.stage in {"shortlisted", "passed"}


class StageStore:
    def __init__(self, run: str = "demo"):
        self.dir = DATA_DIR / "runs" / run / "stages"

    def load(self, candidate_id: str) -> StageRecord:
        p = self.dir / f"{candidate_id}.json"
        if p.exists():
            return StageRecord.model_validate_json(p.read_text())
        return StageRecord(candidate_id=candidate_id)

    def set(self, candidate_id: str, stage: str, actor: str = "recruiter") -> StageRecord:
        if stage not in STAGES:
            return self.load(candidate_id)
        rec = self.load(candidate_id)
        if rec.stage != stage:
            rec.history.append({"from": rec.stage, "to": stage, "actor": actor,
                                "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        rec.stage = stage
        rec.at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{candidate_id}.json").write_text(rec.model_dump_json(indent=2))
        return rec

    def all(self) -> dict[str, StageRecord]:
        if not self.dir.exists():
            return {}
        return {f.stem: StageRecord.model_validate_json(f.read_text())
                for f in self.dir.glob("*.json")}
