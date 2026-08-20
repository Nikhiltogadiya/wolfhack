"""Where the candidate's answers live, and how they reach checkpoint 3."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..config import DATA_DIR
from ..slop.response import CASUAL_QUESTION, Answer


class AnswerSet(BaseModel):
    candidate_id: str
    answers: list[Answer] = Field(default_factory=list)
    submitted_at: str = ""

    @property
    def submitted(self) -> bool:
        return bool(self.submitted_at)

    @property
    def answered_count(self) -> int:
        return sum(1 for a in self.answers if a.text.strip())


class AnswerStore:
    def __init__(self, run: str = "demo"):
        self.dir = DATA_DIR / "runs" / run / "answers"
        self.dir.mkdir(parents=True, exist_ok=True)

    def load(self, candidate_id: str) -> AnswerSet:
        p = self.dir / f"{candidate_id}.json"
        if p.exists():
            return AnswerSet.model_validate_json(p.read_text())
        return AnswerSet(candidate_id=candidate_id)

    def save(self, s: AnswerSet) -> None:
        (self.dir / f"{s.candidate_id}.json").write_text(s.model_dump_json(indent=2))

    def record(self, candidate_id: str, questions: list[str], texts: list[str],
               baseline_text: str) -> AnswerSet:
        """Store a submission. The casual question is stored first and marked as the baseline,
        because checkpoint 3 compares everything else against it."""
        s = self.load(candidate_id)
        s.answers = [Answer(question=CASUAL_QUESTION, text=baseline_text.strip(), is_baseline=True)]
        s.answers += [
            Answer(question=q, text=t.strip())
            for q, t in zip(questions, texts) if t.strip()
        ]
        s.submitted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.save(s)
        return s
