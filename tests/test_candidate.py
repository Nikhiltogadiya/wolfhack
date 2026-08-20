"""Consent and checkpoint 3.

The consent tests are the sixth Responsible-AI bullet. They have to check the fetch does not
HAPPEN, not that its result is hidden afterwards - anything less is a promise we would be
breaking quietly.
"""

from __future__ import annotations

import pytest

from fit_happens.candidate.consent import DEFAULT_GRANTS, SCOPES, Consent, ConsentStore
from fit_happens.schemas import Employment, Span, Verdict
from fit_happens.slop.response import (
    CASUAL_QUESTION, Answer, check_against_cv, check_style_consistency, scan_responses,
)


def _emp(start="2018", end="present"):
    return [Employment(employer="Acme", title="Engineer", start=start, end=end,
                       evidence=Span(text="x"))]


def _consent(**grants) -> Consent:
    c = Consent(token="t", candidate_id="x")
    for k, v in grants.items():
        c.grants[k] = v
    return c


class TestConsent:
    def test_everything_external_is_off_by_default(self):
        assert DEFAULT_GRANTS["cv"] is True
        assert not any(v for k, v in DEFAULT_GRANTS.items() if k != "cv")

    def test_the_cv_cannot_be_switched_off(self):
        """They sent it to apply. Pretending it is optional would be theatre."""
        c = _consent()
        assert c.set("cv", False) is False
        assert c.allows("cv")

    def test_granting_then_revoking_reports_the_revocation(self):
        """The caller needs to know, so it can delete what was gathered under that scope."""
        c = _consent()
        assert c.set("github", True) is False
        assert c.set("github", False) is True
        assert not c.allows("github")

    def test_every_change_is_recorded_with_a_time(self):
        c = _consent()
        c.set("github", True)
        c.set("github", False)
        assert len(c.history) == 2
        assert all(e.at and e.scope == "github" for e in c.history)
        assert [e.granted for e in c.history] == [True, False]

    def test_unknown_scopes_are_rejected(self):
        c = _consent()
        assert c.set("everything", True) is False
        assert "everything" not in c.grants

    def test_tokens_are_not_guessable_from_the_candidate_id(self):
        s = ConsentStore()
        t = s.token_for("priya_raman")
        assert len(t) >= 16 and "priya" not in t

    def test_scope_descriptions_say_what_we_actually_do(self):
        """Shown verbatim to the candidate, so they must be specific enough to act on."""
        for key, meta in SCOPES.items():
            assert len(meta["detail"]) > 40, key
        assert "never read private" in SCOPES["github"]["detail"]


class TestConsentGatesTheFetch:
    def test_github_is_not_fetched_without_consent(self, monkeypatch):
        """The network call must not happen. Fetching then hiding is not consent."""
        from fit_happens import pipeline

        called = []
        monkeypatch.setattr(pipeline.github, "fetch_profile",
                            lambda *a, **k: called.append(1))
        monkeypatch.setattr(pipeline.github, "find_handles", lambda t: ["someone"])
        monkeypatch.setattr(pipeline.credentials, "verify_credentials", lambda *a, **k: [])

        class Doc:
            text = "github.com/someone"

        pipeline.n_verify({"document": Doc(), "claims": [], "requirements": [],
                           "consent": _consent(github=False)})
        assert called == [], "fetched despite consent being withheld"

    def test_github_is_fetched_once_consent_is_given(self, monkeypatch):
        from fit_happens import pipeline

        called = []
        monkeypatch.setattr(pipeline.github, "fetch_profile",
                            lambda *a, **k: called.append(1) or "profile")
        monkeypatch.setattr(pipeline.github, "find_handles", lambda t: ["someone"])
        monkeypatch.setattr(pipeline.github, "verify_claims", lambda *a, **k: [])
        monkeypatch.setattr(pipeline.credentials, "verify_credentials", lambda *a, **k: [])

        class Doc:
            text = "github.com/someone"

        pipeline.n_verify({"document": Doc(), "claims": [], "requirements": [],
                           "consent": _consent(github=True)})
        assert called == [1]

    def test_no_consent_object_means_cv_only(self, monkeypatch):
        """Absent consent must fail closed, not open."""
        from fit_happens import pipeline

        called = []
        monkeypatch.setattr(pipeline.github, "fetch_profile", lambda *a, **k: called.append(1))
        monkeypatch.setattr(pipeline.github, "find_handles", lambda t: ["someone"])
        monkeypatch.setattr(pipeline.credentials, "verify_credentials", lambda *a, **k: [])

        class Doc:
            text = "github.com/someone"

        pipeline.n_verify({"document": Doc(), "claims": [], "requirements": [], "consent": None})
        assert called == []


class TestCheckpoint3:
    def test_consistent_answers_are_clear(self):
        answers = [
            Answer(question=CASUAL_QUESTION, text="Fixed a flaky test suite. It had annoyed everyone.", is_baseline=True),
            Answer(question="Kubernetes?", text="Used it since 2019 at Acme, mostly deployments."),
        ]
        assert scan_responses(answers, [], _emp()).verdict == Verdict.CLEAR

    def test_duration_exceeding_the_career_is_flagged(self):
        a = [Answer(question="q", text="I have 15 years of experience with that.")]
        ids = {f.pattern_id for f in check_against_cv(a, [], _emp())}
        assert "answer_exceeds_career" in ids

    def test_year_before_the_career_started_is_flagged(self):
        a = [Answer(question="q", text="I first did this back in 2005.")]
        assert "answer_predates_career" in {f.pattern_id for f in check_against_cv(a, [], _emp())}

    def test_technology_claim_predating_its_release_is_flagged(self):
        a = [Answer(question="q", text="I have 15 years of Kubernetes experience.")]
        assert "answer_predates_technology" in {f.pattern_id for f in check_against_cv(a, [], _emp())}

    def test_the_baseline_answer_is_never_itself_checked(self):
        """It exists to capture unguarded writing; scrutinising it would defeat the purpose."""
        a = [Answer(question=CASUAL_QUESTION, text="Back in 2005 I had 30 years of Kubernetes.",
                    is_baseline=True)]
        assert check_against_cv(a, [], _emp()) == []

    def test_style_divergence_alone_never_flags(self):
        """People write more carefully about things that matter. That is not dishonesty."""
        answers = [
            Answer(question=CASUAL_QUESTION, text="yeah the ci thing was ok i guess, took a while", is_baseline=True),
            Answer(question="q", text=(
                "I spearheaded a transformative migration, leveraging cutting-edge orchestration "
                "to drive synergy across the organisation, demonstrating strong technical "
                "leadership and a meticulous commitment to world-class engineering standards.")),
        ]
        result = scan_responses(answers, [], _emp())
        assert result.verdict != Verdict.FLAG_FOR_HUMAN

    def test_style_divergence_is_excluded_from_corroboration(self):
        from fit_happens.slop.corroborate import STYLE_ONLY
        assert "style_divergence" in STYLE_ONLY

    def test_cp3_can_never_reject(self):
        a = [Answer(question="q", text="I have 40 years of Kubernetes since 1990.")]
        r = scan_responses(a, [], _emp())
        assert r.verdict in {Verdict.CLEAR, Verdict.INCONCLUSIVE, Verdict.FLAG_FOR_HUMAN}
        assert r.checkpoint == "cp3_response"

    def test_no_answers_is_clear_not_suspicious(self):
        assert scan_responses([], [], _emp()).verdict == Verdict.CLEAR
