"""How current is this profile?

The challenge's second employer pain: *"Stale talent data: profiles are outdated, incomplete or
inactive."* We already compute employment dates for the fit engine, so recency costs nothing -
it was simply never surfaced.

Two things kept deliberately apart, because conflating them would be unfair:

* **Recency** - when the document last describes any activity. A CV whose most recent role
  ended in 2015 is a stale document. That is a fact about the FILE, and a recruiter should
  know it before reading the ranking.
* **Completeness** - how much of the document we could actually parse into dated, attributable
  structure. Low completeness means *we* extracted little, which is a limitation of our
  reading, not a deficiency in the candidate.

Neither feeds the fit score. A career break, a period of caring, illness, study or a layoff all
produce an old end date, and none of them is a reason to rank someone lower. This exists so a
recruiter can see "this CV is five years old, ask for an updated one" - which is a question,
not a judgement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..fit.derived import parse_when
from ..schemas import Employment


@dataclass
class Freshness:
    last_active_year: int | None
    years_since_active: float | None
    dated_roles: int
    total_roles: int
    has_education: bool

    @property
    def completeness(self) -> float:
        """Share of roles we could attach a date to. About our parsing, not about them."""
        return round(self.dated_roles / self.total_roles, 2) if self.total_roles else 0.0

    @property
    def label(self) -> str:
        if self.years_since_active is None:
            return "UNDATED"
        if self.years_since_active < 1.5:
            return "CURRENT"
        if self.years_since_active < 4:
            return "RECENT"
        return "STALE"

    @property
    def tone(self) -> str:
        return {"CURRENT": "green", "RECENT": "green", "UNDATED": "grey", "STALE": "amber"}[self.label]

    @property
    def note(self) -> str:
        if self.years_since_active is None:
            return ("No role on this CV carries a readable date, so we cannot tell how current "
                    "it is. Worth asking for an updated copy.")
        if self.label == "STALE":
            return (f"The most recent dated role ends in {self.last_active_year}, "
                    f"{self.years_since_active:.0f} years ago. The document may simply be out of "
                    f"date - ask for a current one before drawing any conclusion.")
        return f"Most recent dated activity: {self.last_active_year}."


def assess(employment: list[Employment], has_education: bool = False) -> Freshness:
    ends: list[int] = []
    dated = 0
    for e in employment:
        end = parse_when(e.end) or parse_when(e.start)
        if end:
            dated += 1
            ends.append(end.year)
    last = max(ends) if ends else None
    return Freshness(
        last_active_year=last,
        years_since_active=(date.today().year - last) if last else None,
        dated_roles=dated,
        total_roles=len(employment),
        has_education=has_education,
    )
