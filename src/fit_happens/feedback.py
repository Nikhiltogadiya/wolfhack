"""Why a recruiter would not interview someone, captured at the moment they decide.

Intake §9.4: the reasons are the improvement signal, and they have to be recorded *inside the
existing flow* - at the moment of rejection, not in a survey nobody fills in later.

The point is not the textarea. It is that a recruiter passing on a candidate we ranked highly
is telling us something our scoring missed, and that is the only feedback loop we have that
does not require waiting to see who got hired and succeeded.

Explicitly NOT automatic retraining. The reasons accumulate, a human reads them, and thresholds
move deliberately. A system that retrained itself on recruiter rejections would learn whatever
biases those rejections contain, at speed and without anyone noticing.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .config import DATA_DIR

# Fixed reasons, because free text alone cannot be counted and "not a fit" tells us nothing.
# Each maps to a part of the system that would have to change if it recurs.
REASONS: dict[str, dict[str, str]] = {
    "wrong_seniority": {
        "label": "Wrong seniority for the role",
        "signal": "the JD's seniority band is not being scored"},
    "missing_context": {
        "label": "Right skills, wrong context or industry",
        "signal": "domain requirements are under-weighted against skills"},
    "we_misread_the_cv": {
        "label": "We misread their CV",
        "signal": "extraction or mapping error - the most important one to catch"},
    "requirement_not_in_jd": {
        "label": "Needed something the advert never stated",
        "signal": "belongs in the internal JD, where it can be scored and audited"},
    "evidence_too_thin": {
        "label": "Claims were not backed by anything concrete",
        "signal": "evidence density should be more prominent"},
    "already_progressed": {
        "label": "Pipeline reason, nothing to do with fit",
        "signal": "no model change needed - excluded from calibration"},
    "other": {"label": "Something else",
              "signal": "no mapped signal - a human reads the note, and if the same thing "
                        "recurs it earns its own reason"},
}


class Rejection(BaseModel):
    candidate_id: str
    reason: str
    note: str = ""
    fit_score: float = 0.0
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    actor: str = "recruiter"

    @property
    def label(self) -> str:
        return REASONS.get(self.reason, REASONS["other"])["label"]

    @property
    def signal(self) -> str:
        return REASONS.get(self.reason, REASONS["other"])["signal"]

    @property
    def is_our_error(self) -> bool:
        """A rejection that says our reading was wrong, rather than that the person was."""
        return self.reason == "we_misread_the_cv"

    @property
    def contradicts_our_ranking(self) -> bool:
        """We ranked them well and a human passed anyway. Those are the informative ones -
        a rejection at 4% tells us nothing we did not already know."""
        return self.fit_score >= 0.55 and self.reason != "already_progressed"


class FeedbackStore:
    def __init__(self, run: str = "demo"):
        self.dir = DATA_DIR / "runs" / run / "feedback"
        self.dir.mkdir(parents=True, exist_ok=True)

    def record(self, r: Rejection) -> None:
        (self.dir / f"{r.candidate_id}.json").write_text(r.model_dump_json(indent=2))

    def get(self, candidate_id: str) -> Rejection | None:
        p = self.dir / f"{candidate_id}.json"
        return Rejection.model_validate_json(p.read_text()) if p.exists() else None

    def all(self) -> list[Rejection]:
        return [Rejection.model_validate_json(f.read_text()) for f in sorted(self.dir.glob("*.json"))]

    def summary(self) -> dict:
        rs = self.all()
        counts = Counter(r.reason for r in rs)
        return {
            "total": len(rs),
            "by_reason": [(REASONS.get(k, REASONS["other"])["label"], v, REASONS.get(k, REASONS["other"])["signal"])
                          for k, v in counts.most_common()],
            "our_errors": sum(1 for r in rs if r.is_our_error),
            "contradicting": sum(1 for r in rs if r.contradicts_our_ranking),
        }
