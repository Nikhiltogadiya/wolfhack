"""The two-layer job description.

- **External JD** - the public posting, free text, exactly what candidates see.
- **Internal JD** - the private layer, and deliberately NOT free text. It is a list of typed
  constraints drawn from an allowlist, each of which must pass `guard.check_value` before it
  can influence a score.

Both feed one match. Every internal constraint that survives becomes a `Requirement` tagged
`source="internal"`, so the dashboard can show what the public advert alone would have scored
versus what the real preferences score - and a candidate's file records exactly which private
criteria were applied to them.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..schemas import Requirement
from .guard import ALLOWED_FIELDS, check_value


class InternalConstraint(BaseModel):
    field_name: str = Field(description=f"one of: {', '.join(sorted(ALLOWED_FIELDS))}")
    value: str
    weight: float = Field(default=1.0, ge=0.0, le=2.0)
    required: bool = False


class AuditEntry(BaseModel):
    """One line of the record shown on the candidate page and exportable for compliance."""

    at: str
    event: str
    detail: str
    actor: str = "system"


class JobDescription(BaseModel):
    title: str
    external_text: str
    internal: list[InternalConstraint] = []
    audit: list[AuditEntry] = []

    def _log(self, event: str, detail: str) -> None:
        self.audit.append(
            AuditEntry(at=datetime.now(timezone.utc).isoformat(timespec="seconds"), event=event, detail=detail)
        )

    def accepted_internal(self) -> list[InternalConstraint]:
        """Constraints that passed the guard. Refusals are logged, never silently dropped.

        Silent dropping would be the worst of both worlds: the employer believes their
        criterion is being applied, and no record exists of the refusal. Logging it is what
        makes "we checked and declined" a defensible position rather than a claim.
        """
        kept: list[InternalConstraint] = []
        for c in self.internal:
            result = check_value(c.field_name, c.value)
            if result.allowed:
                kept.append(c)
                self._log("internal_constraint_accepted", f"{c.field_name}: {c.value}")
            else:
                self._log(
                    "internal_constraint_REFUSED",
                    f"{c.field_name}: {c.value!r} - refused: {result.reason}",
                )
        return kept

    def internal_requirements(self) -> list[Requirement]:
        return [
            Requirement(
                id=f"int-{i}",
                text=c.value,
                kind="required" if c.required else "preferred",
                category="experience",
                dealbreaker=False,
                source="internal",
            )
            for i, c in enumerate(self.accepted_internal())
        ]

    def blocked_count(self) -> int:
        return sum(1 for e in self.audit if e.event == "internal_constraint_REFUSED")
