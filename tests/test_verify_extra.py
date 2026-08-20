"""Credential verification and profile freshness.

Both close employer pain points the challenge names explicitly. Both are advisory: neither may
lower a score, because absence of a recognised credential or of a recent role is absence of
information, not evidence against a person.
"""

from __future__ import annotations

import pytest

from fit_happens.fit.score import score_fit
from fit_happens.schemas import Claim, Employment, Match, Requirement, Span
from fit_happens.verify.credentials import find_certifications, verify_credentials
from fit_happens.verify.freshness import assess


def _c(i, skill):
    return Claim(id=f"c{i}", skill=skill, evidence=Span(text=skill))


def _e(start, end, title="Engineer"):
    return Employment(employer="Acme", title=title, start=start, end=end, evidence=Span(text="x"))


class TestCredentials:
    @pytest.mark.parametrize("text,expected", [
        ("CompTIA Security+ certified, 2019", "CompTIA Security+"),
        ("Holds CISSP and PMP", "CISSP (ISC2)"),
        ("CCNA (Cisco), renewed 2024", "CCNA (Cisco)"),
        ("Microsoft Certified System Administrator", "MCSA (Microsoft)"),
    ])
    def test_real_credentials_are_recognised(self, text, expected):
        assert expected in {c for c, _ in find_certifications(text)}

    def test_longest_match_wins(self):
        """'comptia security+' must not be reported under the shorter 'security+' key."""
        found = dict(find_certifications("CompTIA Security+"))
        assert "CompTIA Security+" in found

    def test_invented_credential_is_reported_as_malformed(self):
        out = verify_credentials("Certified Kubernetes Expert, 2023")
        bad = [v for v in out if v.state == "unsupported"]
        assert bad and "not how that credential is issued" in bad[0].note

    def test_duties_are_not_reported_as_unverifiable_credentials(self):
        """'employee training' and 'training plan' are duties. Listing them as credentials we
        could not verify is worse than useless - it manufactures doubt about a claim the
        candidate never made."""
        claims = [_c(0, "employee training"), _c(1, "training plan"),
                  _c(2, "training coordination"), _c(3, "application training")]
        assert [v for v in verify_credentials("", claims) if v.state == "unsupported"] == []

    def test_a_credential_is_never_both_verified_and_unverifiable(self):
        """'A+ Certified' was reported unverifiable while 'CompTIA A+' was reported verified -
        the same credential contradicting itself in one panel."""
        out = verify_credentials("A+ Certified since 2015", [_c(0, "A+ Certified")])
        verified = {v.skill for v in out if v.state == "corroborated"}
        unverified = {v.skill for v in out if v.state == "unsupported"}
        assert verified and not (verified & unverified)
        assert not any("a+" in u.lower() for u in unverified)

    def test_unverifiable_list_is_capped(self):
        claims = [_c(i, f"Vendor{i} Certified Engineer") for i in range(12)]
        out = verify_credentials("", claims, max_unverifiable=3)
        listed = [v for v in out if v.state == "unsupported"]
        assert len(listed) <= 4  # 3 + one summary row
        assert any("further credentials" in v.skill for v in listed)

    def test_unrecognised_is_worded_as_our_limit_not_their_fault(self):
        out = verify_credentials("", [_c(0, "Brocade Certified Network Professional")])
        assert "says nothing about whether it is genuine" in out[0].note


class TestFreshness:
    def test_old_cv_is_marked_stale(self):
        f = assess([_e("2008", "2015")])
        assert f.label == "STALE"
        assert f.last_active_year == 2015
        assert "ask for a current one" in f.note

    def test_current_cv(self):
        assert assess([_e("2020", "present")]).label == "CURRENT"

    def test_undated_cv_is_undated_not_stale(self):
        """No date is not an old date. Guessing would penalise a formatting choice."""
        f = assess([_e(None, None)])
        assert f.label == "UNDATED"
        assert "cannot tell" in f.note

    def test_completeness_is_about_our_parsing(self):
        f = assess([_e("2020", "2022"), _e(None, None), _e("2015", "2018")])
        assert f.completeness == pytest.approx(0.67, abs=0.01)

    def test_freshness_never_touches_the_fit_score(self):
        """A career break, caring, illness or a layoff all produce an old end date. None of
        them is a reason to rank someone lower."""
        reqs = [Requirement(id="r0", text="x", kind="required", category="skill")]
        matches = [Match(requirement_id="r0", strength="strong")]
        baseline = score_fit(matches, reqs).score
        for emp in ([_e("2008", "2015")], [_e("2024", "present")], [_e(None, None)]):
            assess(emp)
            assert score_fit(matches, reqs).score == baseline

    def test_freshness_fields_are_not_in_the_fit_score_type(self):
        from fit_happens.schemas import FitScore
        banned = {"fresh", "stale", "recency", "last_active", "credential"}
        for name in FitScore.model_fields:
            assert not any(b in name.lower() for b in banned), name
