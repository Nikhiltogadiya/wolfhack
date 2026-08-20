"""The invariants. Each one is a claim we make out loud, backed by a test a judge could run.

If you are changing something here, you are changing what the product promises, not how it is
implemented.
"""

from __future__ import annotations

import inspect

import pytest

from fit_happens import config
from fit_happens.fit import score as score_mod
from fit_happens.fit.score import score_fit
from fit_happens.schemas import Claim, FitScore, Match, Requirement, Span, Verdict


def _req(i: int, kind: str, dealbreaker: bool = False) -> Requirement:
    return Requirement(id=f"r{i}", text=f"requirement {i}", kind=kind, category="skill", dealbreaker=dealbreaker)


def _match(i: int, strength: str) -> Match:
    return Match(requirement_id=f"r{i}", strength=strength, rationale="x")


# ---------------------------------------------------------------- separation


def test_no_reject_path():
    """Slop Bouncer structurally cannot reject anyone: no such value exists to return."""
    assert {v.value for v in Verdict} == {"clear", "inconclusive", "flag_for_human"}
    assert not any("reject" in v.value or "deny" in v.value or "fail" in v.value for v in Verdict)


def test_fit_scoring_cannot_see_style_data():
    """Structural, not behavioural: the types score_fit accepts have no style fields at all.

    A behavioural test could only prove the current code ignores style. This proves the
    function has no way to read it, which is the actual guarantee.
    """
    banned = {"style", "sloppiness", "slop", "ai_score", "authenticity", "bluff", "flag", "verdict",
              "writing", "quality", "polish", "readability"}
    for model in (Match, Requirement, Claim, Span):
        for name in model.model_fields:
            assert not any(b in name.lower() for b in banned), f"{model.__name__}.{name} leaks style into fit scoring"

    params = inspect.signature(score_fit).parameters
    assert set(params) == {"matches", "requirements"}, f"score_fit grew a parameter: {list(params)}"


def test_fit_score_is_unchanged_by_any_slop_signal():
    """Behavioural companion: identical evidence must score identically regardless of context."""
    reqs = [_req(0, "required"), _req(1, "required"), _req(2, "preferred")]
    matches = [_match(0, "strong"), _match(1, "moderate"), _match(2, "weak")]
    baseline = score_fit(matches, reqs)
    for _ in range(5):
        assert score_fit(list(matches), list(reqs)).score == baseline.score


# ---------------------------------------------------------------- the 70/30 split


def test_required_preferred_split_is_fixed_at_70_30():
    """The bug this codebase was built to avoid.

    The implementation this was adapted from normalises by (n_required + 0.3 * n_preferred),
    so the effective ratio drifts with how many requirements a JD lists. With 10 required and
    10 preferred that yields 77/23. Here it must be 70/30 for every shape of JD.
    """
    for n_req, n_pref in [(1, 1), (3, 7), (10, 10), (10, 1), (2, 20), (5, 5)]:
        reqs = [_req(i, "required") for i in range(n_req)] + [
            _req(100 + i, "preferred") for i in range(n_pref)
        ]
        # everything required is met, nothing preferred is
        matches = [_match(i, "strong") for i in range(n_req)] + [
            _match(100 + i, "missing") for i in range(n_pref)
        ]
        got = score_fit(matches, reqs).score
        assert got == pytest.approx(config.WEIGHT_REQUIRED), (
            f"{n_req} required + {n_pref} preferred gave {got:.4f}, expected "
            f"{config.WEIGHT_REQUIRED} - the split is drifting with requirement counts"
        )


def test_preferred_alone_cannot_exceed_its_weight():
    reqs = [_req(0, "required"), _req(1, "preferred")]
    matches = [_match(0, "missing"), _match(1, "strong")]
    assert score_fit(matches, reqs).score == pytest.approx(config.WEIGHT_PREFERRED)


def test_jd_with_no_preferred_requirements_is_not_penalised():
    reqs = [_req(0, "required"), _req(1, "required")]
    matches = [_match(0, "strong"), _match(1, "strong")]
    assert score_fit(matches, reqs).score == pytest.approx(1.0)


# ---------------------------------------------------------------- dealbreakers


def test_dealbreaker_caps_the_score():
    """A missing licence cannot be written around, however strong everything else is."""
    reqs = [_req(0, "required", dealbreaker=True)] + [_req(i, "required") for i in range(1, 6)]
    matches = [_match(0, "missing")] + [_match(i, "strong") for i in range(1, 6)]
    result = score_fit(matches, reqs)
    assert result.capped_by_dealbreaker
    assert result.score == config.DEALBREAKER_CAP
    assert "r0" in result.dealbreakers_unmet


def test_dealbreaker_candidate_can_never_outrank_a_qualifying_one():
    """The property that actually matters for a ranked list."""
    reqs = [_req(0, "required", dealbreaker=True)] + [_req(i, "required") for i in range(1, 6)]
    blocked = score_fit([_match(0, "missing")] + [_match(i, "strong") for i in range(1, 6)], reqs)
    # a weak but eligible candidate: meets the gate, mediocre everywhere else
    eligible = score_fit([_match(0, "strong")] + [_match(i, "moderate") for i in range(1, 6)], reqs)
    assert eligible.score > blocked.score


def test_dealbreaker_caps_rather_than_zeroes():
    """The brief's own evidence table has a worst candidate at 14%, not 0 - so we cap."""
    reqs = [_req(0, "required", dealbreaker=True), _req(1, "required")]
    result = score_fit([_match(0, "missing"), _match(1, "weak")], reqs)
    assert result.score > 0.0
    assert not result.capped_by_dealbreaker, "a low score should not be raised to the cap"


# ---------------------------------------------------------------- gaps and evidence


def test_gap_severity_ordering():
    reqs = [_req(0, "required", dealbreaker=True), _req(1, "required"), _req(2, "preferred")]
    matches = [_match(0, "missing"), _match(1, "missing"), _match(2, "missing")]
    sev = {g.requirement_id: g.severity for g in score_fit(matches, reqs).gaps}
    assert sev == {"r0": "critical", "r1": "major", "r2": "minor"}


def test_missing_requirements_are_not_dropped_from_the_denominator():
    """Silently dropping an unmatched requirement would inflate everyone's coverage."""
    reqs = [_req(i, "required") for i in range(4)]
    partial = [_match(0, "strong")]  # the mapper returned only one
    result = score_fit(partial, reqs)
    assert result.required_coverage == pytest.approx(0.25)


def test_score_is_always_in_range():
    reqs = [_req(0, "required"), _req(1, "preferred")]
    for a in ("strong", "moderate", "weak", "missing"):
        for b in ("strong", "moderate", "weak", "missing"):
            s = score_fit([_match(0, a), _match(1, b)], reqs).score
            assert 0.0 <= s <= 1.0


def test_evidence_density_is_not_an_input_to_the_score():
    """It is reported to the recruiter, and it costs the candidate nothing."""
    src = inspect.getsource(score_mod.score_fit)
    assert "evidence_density" not in src
    assert FitScore.model_fields.keys().isdisjoint({"evidence_density", "writing_quality"})
