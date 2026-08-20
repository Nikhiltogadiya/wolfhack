"""GitHub verification.

The fairness tests here are not optional extras - they are the reason this feature is
defensible at all. A verification system that quietly penalises people for having no public
code would discriminate against anyone working under an NDA, on closed source, in a
non-engineering role, or early in their career.
"""

from __future__ import annotations

import pytest

from fit_happens import config
from fit_happens.fit.score import score_fit
from fit_happens.schemas import (
    Claim, ExternalEvidence, ExternalProfile, Match, Requirement, Span,
)
from fit_happens.verify.github import GENERIC_TOPICS, find_handles, verify_claims


def _c(i, skill):
    return Claim(id=f"c{i}", skill=skill, evidence=Span(text=skill))


def _ev(name, n=5, first=2018, last=2026):
    return ExternalEvidence(name=name, volume=n, first_seen_year=first, last_seen_year=last,
                            detail=f"{n} public repo(s), {first}-{last}")


PROFILE = ExternalProfile(handle="someone", found=True, public_repos=12,
                          evidence=[_ev("Python", 20), _ev("Docker", 9), _ev("Rust", 4)])


# ---------------------------------------------------------------- the fairness rule


class TestAbsenceIsNeverNegative:
    def test_no_profile_produces_no_verifications_at_all(self):
        """Not a page of 'unsupported' rows, which would read as suspicion. Nothing."""
        assert verify_claims([_c(0, "Python")], ExternalProfile(handle="x", found=False)) == []

    def test_profile_that_errored_produces_nothing(self):
        p = ExternalProfile(handle="x", found=False, error="ConnectError: dns failure")
        assert verify_claims([_c(0, "Python")], p) == []

    def test_found_but_empty_profile_produces_nothing(self):
        assert verify_claims([_c(0, "Python")], ExternalProfile(handle="x", found=True)) == []

    def test_missing_github_never_lowers_any_score(self):
        """The headline invariant. Fit scoring must be byte-identical with and without any
        external evidence - which is structurally true, because score_fit cannot see it."""
        reqs = [Requirement(id="r0", text="Python", kind="required", category="skill"),
                Requirement(id="r1", text="Docker", kind="preferred", category="skill")]
        matches = [Match(requirement_id="r0", strength="strong"),
                   Match(requirement_id="r1", strength="moderate")]
        with_profile = score_fit(matches, reqs)
        verify_claims([_c(0, "Python")], ExternalProfile(handle="x", found=False))
        without = score_fit(matches, reqs)
        assert with_profile.score == without.score
        assert "github" not in str(with_profile.model_dump()).lower()

    def test_unsupported_is_worded_as_no_information_not_as_doubt(self):
        v = next(v for v in verify_claims([_c(0, "COBOL")], PROFILE) if v.state == "unsupported")
        assert "not a mark against" in v.note
        assert "no public repository evidence" in v.note


# ---------------------------------------------------------------- the three states


def test_claim_with_matching_repos_is_corroborated():
    v = next(v for v in verify_claims([_c(0, "Python")], PROFILE) if v.skill == "Python")
    assert v.state == "corroborated"
    assert v.evidence and "2018" in v.note or "public repositories" in v.note


def test_claim_with_no_repos_is_unsupported_not_contradicted():
    v = next(v for v in verify_claims([_c(0, "COBOL")], PROFILE) if v.skill == "COBOL")
    assert v.state == "unsupported"


def test_real_evidence_not_on_the_resume_is_undersold():
    out = verify_claims([_c(0, "Python")], PROFILE)
    assert {v.skill for v in out if v.state == "undersold"} >= {"Docker"}


def test_undersold_is_filtered_to_what_the_role_needs():
    reqs = [Requirement(id="r0", text="Containerisation with Docker", kind="required", category="skill")]
    out = verify_claims([_c(0, "Python")], PROFILE, reqs)
    undersold = {v.skill for v in out if v.state == "undersold"}
    assert "Docker" in undersold
    assert "Rust" not in undersold, "irrelevant evidence should not be surfaced"


def test_undersold_is_capped():
    big = ExternalProfile(handle="x", found=True, evidence=[_ev(f"Lang{i}", 9) for i in range(40)])
    out = verify_claims([_c(0, "Python")], big, None, max_undersold=3)
    assert sum(1 for v in out if v.state == "undersold") == 3


def test_generic_topics_are_not_reported_as_skills():
    """One active profile yielded fifty undersold rows - json, http, server, backend - which
    buried the two that meant anything."""
    noisy = ExternalProfile(handle="x", found=True,
                            evidence=[_ev("json", 9), _ev("http", 9), _ev("backend", 9), _ev("Rust", 9)])
    undersold = {v.skill for v in verify_claims([_c(0, "Python")], noisy) if v.state == "undersold"}
    assert undersold == {"Rust"}
    assert "json" in GENERIC_TOPICS


# ---------------------------------------------------------------- handles


@pytest.mark.parametrize("text,expected", [
    ("github.com/torvalds", ["torvalds"]),
    ("https://github.com/some-user/repo", ["some-user"]),
    ("see github.com/features/actions for CI", []),
    ("no links at all", []),
    ("github.com/a-dev and github.com/a-dev again", ["a-dev"]),
])
def test_find_handles(text, expected):
    assert find_handles(text) == expected
