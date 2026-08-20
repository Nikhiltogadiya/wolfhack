"""Turn matches into one fit score.

This module is the reason the product's central claim is true. Look at what `score_fit` takes:
`list[Match]` and `list[Requirement]`. Neither type has a style field, a sloppiness score, or
an authenticity flag - so writing quality cannot influence the number. It is not that we choose
not to use it; the function cannot see it.

Two deliberate departures from the code this was adapted from:

1. **The 70/30 split is fixed.** ai-CV-cover-letter normalises by `must_max + nice_max` with a
   per-item multiplier, which makes the ratio drift with how many requirements a JD happens to
   list - 10 required + 10 preferred yields 77/23, not 70/30. Coverage is computed within each
   bucket first, then combined at fixed weights.
2. **Preferred coverage is scored on the same extracted evidence as required.** The brief
   admits poor writing costs a few points on preferred scoring, which contradicts its own first
   house rule. Scoring both buckets off the same typed claims removes the leak rather than
   documenting it. Evidence *density* is reported separately and scores nothing.
"""

from __future__ import annotations

from .. import config
from ..schemas import FitScore, Gap, Match, Requirement


def _coverage(matches: list[Match], requirements: list[Requirement], kind: str) -> float | None:
    subset = [r for r in requirements if r.kind == kind]
    if not subset:
        return None
    by_id = {m.requirement_id: m for m in matches}
    earned = sum(config.STRENGTH_CREDIT.get(by_id[r.id].strength, 0.0) for r in subset if r.id in by_id)
    return earned / len(subset)


def classify_gaps(matches: list[Match], requirements: list[Requirement]) -> list[Gap]:
    """critical = an unmet hard gate; major = a missing required; minor = a missing preferred."""
    by_id = {m.requirement_id: m for m in matches}
    gaps: list[Gap] = []
    for r in requirements:
        m = by_id.get(r.id)
        if m is None or m.strength == "strong":
            continue
        if r.dealbreaker and m.strength in {"missing", "weak"}:
            severity = "critical"
        elif r.kind == "required" and m.strength == "missing":
            severity = "major"
        elif r.kind == "required" and m.strength == "weak":
            severity = "major"
        elif m.strength in {"missing", "weak"}:
            severity = "minor"
        else:
            continue
        gaps.append(Gap(requirement_id=r.id, severity=severity, text=r.text))  # type: ignore[arg-type]
    return gaps


def score_fit(matches: list[Match], requirements: list[Requirement]) -> FitScore:
    req_cov = _coverage(matches, requirements, "required")
    pref_cov = _coverage(matches, requirements, "preferred")

    # A JD with no preferred requirements must not be penalised for the empty bucket, and a JD
    # with no required ones must not have the whole score vanish.
    if req_cov is None and pref_cov is None:
        raw = 0.0
    elif pref_cov is None:
        raw = req_cov or 0.0
    elif req_cov is None:
        raw = pref_cov
    else:
        raw = config.WEIGHT_REQUIRED * req_cov + config.WEIGHT_PREFERRED * pref_cov

    by_id = {m.requirement_id: m for m in matches}
    unmet = [
        r.id for r in requirements
        if r.dealbreaker and by_id.get(r.id) and by_id[r.id].strength in {"missing", "weak"}
    ]

    capped = bool(unmet) and raw > config.DEALBREAKER_CAP
    score = config.DEALBREAKER_CAP if capped else raw

    return FitScore(
        score=round(score, 4),
        required_coverage=round(req_cov or 0.0, 4),
        preferred_coverage=round(pref_cov or 0.0, 4),
        matches=matches,
        gaps=classify_gaps(matches, requirements),
        dealbreakers_unmet=unmet,
        capped_by_dealbreaker=capped,
    )


def evidence_density(claims_with_spans: int, total_claims: int) -> float:
    """How much of the resume is backed by quotable evidence.

    Reported to the recruiter as context, and deliberately NOT an input to score_fit. This is
    the honest home for "this resume is thin": visible, but costing the candidate nothing.
    """
    return round(claims_with_spans / total_claims, 3) if total_claims else 0.0
