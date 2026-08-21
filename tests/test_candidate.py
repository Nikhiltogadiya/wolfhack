"""Consent and checkpoint 3.

The consent tests are the sixth Responsible-AI bullet. They have to check the fetch does not
HAPPEN, not that its result is hidden afterwards - anything less is a promise we would be
breaking quietly.
"""

from __future__ import annotations

import typing

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


class TestNewFiguresUnderQuestioning:
    """Set membership of numbers between two documents - the check `check_claims` does well and
    date arithmetic cannot do at all. Finished late: it was noted in a comment and then not
    built, which is why it gets its own tests rather than a mention."""

    CV = ("Platform Engineer at Acme 2018-2026. Ran migration of 11 services. "
          "Cut deploy time 35%. Team of 6.")

    def _flags(self, text):
        from fit_happens.slop.response import new_numbers_under_questioning
        return new_numbers_under_questioning([Answer(question="q", text=text)], self.CV)

    def test_a_figure_already_in_the_cv_is_not_new(self):
        assert self._flags("I migrated 11 services and cut deploy time 35%.") == []

    def test_a_figure_appearing_only_under_questioning_is_flagged(self):
        f = self._flags("I led a team of 40 and cut costs by 60%.")
        assert f and "40" in f[0].description and "60" in f[0].description

    def test_trivial_numbers_are_ignored(self):
        """Without this every 'there were 2 problems' becomes a finding."""
        assert self._flags("There were 2 main problems and I fixed both.") == []

    def test_years_are_left_to_the_date_checks(self):
        assert self._flags("I did that in 2019.") == []

    def test_the_baseline_answer_is_exempt(self):
        from fit_happens.slop.response import new_numbers_under_questioning
        a = [Answer(question="q", text="I led 40 people", is_baseline=True)]
        assert new_numbers_under_questioning(a, self.CV) == []

    def test_no_cv_text_means_no_flags(self):
        from fit_happens.slop.response import new_numbers_under_questioning
        assert new_numbers_under_questioning([Answer(question="q", text="40 people")], "") == []

    def test_a_new_figure_alone_never_reaches_flag_for_human(self):
        """People legitimately add detail when asked - that is why we asked."""
        answers = [Answer(question=CASUAL_QUESTION, text="the CI work was fun", is_baseline=True),
                   Answer(question="q", text="I led a team of 40 and cut costs by 60%.")]
        r = scan_responses(answers, [], _emp(), self.CV)
        assert r.verdict != Verdict.FLAG_FOR_HUMAN

    def test_several_patterns_on_one_sentence_stay_one_observation(self):
        """Three rules firing on the same sentence is one oddity, not three. Written as a
        corroboration test by mistake first - the code was right and the expectation was not."""
        answers = [Answer(question=CASUAL_QUESTION, text="ci work", is_baseline=True),
                   Answer(question="q", text="I led a team of 40 and have 25 years of Kubernetes.")]
        r = scan_responses(answers, [], _emp(), self.CV)
        assert len({f.pattern_id for f in r.flags}) >= 3, "expected several patterns to fire"
        assert r.verdict == Verdict.INCONCLUSIVE, "same span must not corroborate itself"

    def test_it_corroborates_with_a_flag_on_a_DIFFERENT_answer(self):
        """Two findings on two different answers are genuinely independent."""
        answers = [
            Answer(question=CASUAL_QUESTION, text="ci work", is_baseline=True),
            Answer(question="team?", text="I led a team of 40 people there."),
            Answer(question="k8s?", text="Kubernetes, about 25 years now."),
        ]
        r = scan_responses(answers, [], _emp(), self.CV)
        ids = {f.pattern_id for f in r.flags}
        assert {"new_figures_in_answer", "answer_predates_technology"} <= ids
        assert r.verdict == Verdict.FLAG_FOR_HUMAN


def test_every_consent_scope_actually_changes_behaviour():
    """A consent control that nothing reads is worse than an absent one: it makes the exact
    claim this module exists to make, falsely. A 'community' scope was declared and read by
    nothing until this test was written."""
    import inspect

    from fit_happens import pipeline
    from fit_happens.candidate.consent import SCOPES

    source = inspect.getsource(pipeline.n_verify)
    for scope in SCOPES:
        if SCOPES[scope]["locked"]:
            continue  # the CV is always in scope by definition
        assert f'allows("{scope}")' in source, (
            f"consent scope {scope!r} is offered to candidates but no code reads it")


def _isolated_store(tmp_path, monkeypatch):
    from fit_happens.candidate import consent as consent_mod

    monkeypatch.setattr(consent_mod, "DATA_DIR", tmp_path)
    return ConsentStore("demo")


def test_granting_a_scope_triggers_the_fetch_it_authorises(tmp_path, monkeypatch):
    """The test above greps n_verify's source, which answers "does this string appear" - not
    "does granting change anything". It passed all the way through the release in which
    granting did nothing whatsoever: consent was read only inside run_candidate, which had
    finished long before the candidate ever touched the toggle. The pill flipped to SHARING
    and no repo was ever fetched.

    So this one exercises the route instead: grant, and assert the re-verification is actually
    scheduled for this candidate.
    """
    from fastapi.testclient import TestClient

    from fit_happens.web import app as web

    store = _isolated_store(tmp_path, monkeypatch)
    store.save(store.load("ada"))  # by_token scans saved records, not derived ids
    assert not store.load("ada").allows("github")
    token = store.token_for("ada")

    scheduled: list[tuple[str, str]] = []
    monkeypatch.setattr(web.tasks, "reverify",
                        lambda slug, cid: scheduled.append((slug, cid)))

    r = TestClient(web.app).post(f"/apply/{token}/consent",
                                 data={"scope": "github", "granted": "on"},
                                 follow_redirects=False)

    assert r.status_code == 303, r.status_code
    assert store.load("ada").allows("github"), "the grant was not persisted"
    assert scheduled == [("demo", "ada")], (
        "granting a scope must trigger the fetch it authorises; nothing was scheduled")


def test_revoking_a_scope_schedules_no_fetch(tmp_path, monkeypatch):
    """The mirror: withdrawal deletes what was gathered, it must never go and get more."""
    from fastapi.testclient import TestClient

    from fit_happens.web import app as web

    store = _isolated_store(tmp_path, monkeypatch)
    c = store.load("ada")
    c.set("github", True)
    store.save(c)
    token = store.token_for("ada")

    scheduled: list[tuple[str, str]] = []
    monkeypatch.setattr(web.tasks, "reverify",
                        lambda slug, cid: scheduled.append((slug, cid)))

    TestClient(web.app).post(f"/apply/{token}/consent",
                             data={"scope": "github", "granted": ""},
                             follow_redirects=False)

    assert not store.load("ada").allows("github")
    assert scheduled == [], "revoking must not trigger a fetch"


def test_revoking_deletes_only_the_revoking_candidates_cache(tmp_path, monkeypatch):
    """Withdrawal globbed every `gh_*.json` in the shared cache, so one candidate revoking
    GitHub deleted the cached lookups of every candidate in every role - and left their
    `verifications` rows in place, making the deletion both too broad and incomplete."""
    from fit_happens import config
    from fit_happens.verify import github

    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(github.config, "CACHE_DIR", tmp_path)

    mine = github._cache_path("ada-l")
    theirs = github._cache_path("grace-h")
    mine.write_text("{}")
    theirs.write_text("{}")

    deleted = github.forget("CV text mentioning github.com/ada-l only")

    assert deleted == 1
    assert not mine.exists(), "the revoking candidate's cache should be gone"
    assert theirs.exists(), "another candidate's cache must never be deleted"


def test_a_retired_scope_on_disk_does_not_crash_the_portal():
    """SCOPES shrank once and the records written before that still name the removed scope.
    `summary()` maps SCOPES[k]["label"] over the stored grants, so a retired scope set to true
    raised KeyError and 500'd the candidate's own portal. Live data was one flag away from it:
    two demo records still carry "community": false, latent only because it is false."""
    c = Consent(token="t", candidate_id="ada",
                grants={"cv": True, "community": True, "github": False})

    assert "community" not in c.grants, "a scope no longer offered must not survive a load"
    assert c.summary()  # would have raised KeyError
    assert not c.allows("community")


class TestHandleFormsOnRealCVs:
    """Only `github.com/x` URLs were matched, so a CV saying "GitHub: janedoe" - one of the
    most common ways anyone writes it - yielded no handle and the candidate was treated
    exactly like someone with no public code. Hard rule 5 says absence of GitHub must never
    cost a candidate; a regex that manufactures that absence turns the rule into a lie for
    everyone who did not paste a full URL."""

    FOUND: typing.ClassVar[list[str]] = [
        "github.com/janedoe", "https://github.com/janedoe", "www.github.com/janedoe",
        "github.com/janedoe/portfolio", "GitHub: janedoe", "Github: janedoe",
        "GitHub - janedoe", "GitHub \u2014 janedoe", "GitHub Profile: janedoe",
        "GitHub profile: @janedoe", "GitHub username: jane99", "Portfolio: github.com/jane-doe-99",
    ]
    # An explicit separator is required precisely so these stay empty.
    NOT_FOUND: typing.ClassVar[list[str]] = [
        "I have used GitHub for 5 years", "Experience with GitHub Actions and CI",
        "Tools: Git, GitHub, GitLab", "GitHub: available on request",
        "Migrated the team to GitHub - a six month project", "GitHub and Jenkins pipelines",
    ]

    def test_the_ways_people_actually_write_it_are_found(self):
        from fit_happens.verify.github import find_handles

        for text in self.FOUND:
            assert find_handles(text), f"no handle found in {text!r}"

    def test_prose_that_merely_mentions_github_yields_nothing(self):
        from fit_happens.verify.github import find_handles

        for text in self.NOT_FOUND:
            assert not find_handles(text), f"false handle in {text!r}: {find_handles(text)}"
