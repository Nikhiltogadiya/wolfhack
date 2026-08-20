"""Slop Bouncer: style, bluff patterns, and the corroboration rule.

The corroboration tests are the ones that matter. They are the difference between a tool that
flags a typo as fraud and one a hiring team can defend using.
"""

from __future__ import annotations

import pytest

from fit_happens.schemas import Claim, Employment, Flag, Span, StyleRead, Verdict
from fit_happens.slop import bluff
from fit_happens.slop.corroborate import decide, independent
from fit_happens.slop.style import read_style


def _f(pattern_id: str, span: str, conf: float = 0.6) -> Flag:
    return Flag(pattern_id=pattern_id, description="d", span=Span(text=span), confidence=conf)


def _claim(skill: str, years=None, since=None) -> Claim:
    return Claim(id="c", skill=skill, years_claimed=years, since_year=since,
                 evidence=Span(text=f"{skill} experience"))


def _emp(title, start, end, employer="Acme", full_time=True) -> Employment:
    return Employment(employer=employer, title=title, start=start, end=end,
                      full_time=full_time, evidence=Span(text=title))


# ---------------------------------------------------------------- corroboration


class TestCorroboration:
    def test_one_flag_is_never_enough(self):
        r = decide([_f("overlapping_employment", "line A")])
        assert r.verdict == Verdict.INCONCLUSIVE

    def test_two_flags_of_the_same_pattern_are_not_independent(self):
        """One rule firing twice is one observation, not two."""
        r = decide([_f("overlapping_employment", "line A"), _f("overlapping_employment", "line B")])
        assert r.verdict == Verdict.INCONCLUSIVE

    def test_two_patterns_on_the_same_span_are_not_independent(self):
        """One odd line tripping two rules is one oddity, not a pattern of dishonesty."""
        r = decide([_f("round_numbers", "the same line"), _f("jd_echo", "the same line")])
        assert r.verdict == Verdict.INCONCLUSIVE

    def test_two_distinct_patterns_on_distinct_spans_corroborate(self):
        r = decide([_f("expertise_predates_technology", "line A"), _f("duplicate_bullet", "line B")])
        assert r.verdict == Verdict.FLAG_FOR_HUMAN

    def test_the_verdict_names_which_flags_corroborated(self):
        """'It always names which ones' - the brief."""
        r = decide([_f("expertise_predates_technology", "line A"), _f("duplicate_bullet", "line B")])
        assert "expertise_predates_technology" in r.reason
        assert "duplicate_bullet" in r.reason

    def test_flagging_is_never_a_rejection(self):
        r = decide([_f("expertise_predates_technology", "A"), _f("duplicate_bullet", "B")])
        assert r.verdict == Verdict.FLAG_FOR_HUMAN
        assert "not a rejection" in r.reason.lower()

    def test_no_flags_is_clear(self):
        assert decide([]).verdict == Verdict.CLEAR


class TestStyleIsNeverEvidence:
    def test_maximum_style_score_alone_cannot_flag(self):
        """The house rule, and the reason it exists: a 61% false-positive rate for non-native
        English writers means style can never be allowed to convict anyone."""
        style = StyleRead(score=1.0, band="high", word_count=500, patterns_fired=[
            _f("stock_phrases", "a"), _f("self_significance", "b"),
            _f("negative_parallelism", "c"), _f("uniform_rhythm", "d"),
        ])
        r = decide([], style)
        assert r.verdict == Verdict.INCONCLUSIVE

    def test_style_flags_are_excluded_from_corroboration(self):
        style_flags = [_f("stock_phrases", "a"), _f("uniform_rhythm", "b"), _f("rule_of_three", "c")]
        assert independent(style_flags) == []

    def test_style_cannot_top_up_a_single_real_flag(self):
        """One genuine inconsistency plus heavy style must still be inconclusive."""
        style = StyleRead(score=1.0, band="high", word_count=500,
                          patterns_fired=[_f("stock_phrases", "a"), _f("uniform_rhythm", "b")])
        r = decide([_f("round_numbers", "line X")], style)
        assert r.verdict == Verdict.INCONCLUSIVE


# ---------------------------------------------------------------- deterministic patterns


class TestDeterministicPatterns:
    def test_expertise_predating_the_technology(self):
        flags = bluff.expertise_predates_technology([_claim("Kubernetes", since=2009)])
        assert flags and "2014" in flags[0].description

    def test_plausible_technology_claim_does_not_fire(self):
        assert not bluff.expertise_predates_technology([_claim("Kubernetes", since=2018)])

    def test_unknown_technology_does_not_fire(self):
        """We only flag what we can prove. An absent entry is not evidence."""
        assert not bluff.expertise_predates_technology([_claim("Widgetron 9000", since=1990)])

    def test_expertise_predating_the_career(self):
        flags = bluff.expertise_predates_career([_claim("Python", since=2005)], [_emp("Dev", "2015", "2020")])
        assert flags

    def test_study_era_use_is_not_flagged(self):
        """One year of grace: people genuinely use tools before their first job."""
        assert not bluff.expertise_predates_career([_claim("Python", since=2014)], [_emp("Dev", "2015", "2020")])

    def test_overlapping_full_time_roles(self):
        """Different employers - two genuinely concurrent full-time jobs."""
        assert bluff.overlapping_employment(
            [_emp("A", "2015", "2020", employer="Acme"), _emp("B", "2017", "2019", employer="Globex")])

    def test_short_handover_overlap_is_not_flagged(self):
        assert not bluff.overlapping_employment(
            [_emp("A", "2015-01", "2018-03", employer="Acme"),
             _emp("B", "2018-01", "2020-01", employer="Globex")])

    def test_part_time_overlap_is_not_flagged(self):
        assert not bluff.overlapping_employment(
            [_emp("A", "2015", "2020", employer="Acme"),
             _emp("B", "2017", "2019", employer="Globex", full_time=False)])

    def test_duplicate_bullet_across_roles(self):
        text = ("Managed the migration of eleven services to Kubernetes\n"
                "Some other line entirely here\n"
                "Managed the migration of eleven services to Kubernetes\n")
        assert bluff.duplicate_bullets(text)

    def test_round_numbers(self):
        assert bluff.round_number_density("Cut costs 50% and 30%, grew 20%, saved 100, hit 40%, raised 60%")

    def test_real_measurements_do_not_fire(self):
        assert not bluff.round_number_density("Cut costs 47% and 31%, grew 18%, saved 112, hit 43%, raised 62%")

    @pytest.mark.parametrize("text", [
        "Certified Kubernetes Expert", "AWS Certified Master", "CISSP Level 3",
        "Certified Scrum Ninja",
    ])
    def test_invented_credentials(self, text):
        assert bluff.impossible_certification(text)

    @pytest.mark.parametrize("text", [
        "CISSP", "CompTIA Security+", "CKA", "AWS Certified Solutions Architect - Associate",
        "PMP", "CCNA",
    ])
    def test_real_credentials_do_not_fire(self, text):
        assert not bluff.impossible_certification(text)


class TestStyleReader:
    def test_short_text_is_not_scored_at_all(self):
        """A bullet is 10-25 words. Detectors need 100+. Refusing to score is the honest
        answer; reporting 'clean' would be a lie."""
        r = read_style("Ran the Kubernetes migration for the logistics platform.")
        assert r.score == 0.0
        assert "below" in r.caveat and "not as clean" in r.caveat

    def test_the_caveat_is_always_present_on_a_real_score(self):
        r = read_style(" ".join(["Delivered robust seamless solutions across the platform."] * 40))
        assert "false-positive" in r.caveat and "non-native" in r.caveat

    def test_every_pattern_carries_a_span(self):
        r = read_style(" ".join(["Spearheaded transformative synergy, demonstrating strong leadership."] * 30))
        assert r.patterns_fired
        for f in r.patterns_fired:
            assert f.span.text.strip(), f"{f.pattern_id} fired with no evidence span"


class TestOverlapDoesNotAccuseOnBadData:
    """Every one of these came from real corpus data, not imagination."""

    def test_anonymised_employers_are_skipped(self):
        """Public resume corpora replace employers with 'Company Name'. Two roles at the same
        placeholder are not concurrent employment - they are two unknown employers."""
        emp = [_emp("Analyst", "2000", "present", employer="Company Name"),
               _emp("Manager", "2005", "present", employer="Company Name")]
        assert not bluff.overlapping_employment(emp)

    @pytest.mark.parametrize("name", ["Company", "N/A", "Confidential", "Various", "Self-employed", "-"])
    def test_other_placeholder_employers_are_skipped(self, name):
        emp = [_emp("A", "2010", "2020", employer=name), _emp("B", "2012", "2018", employer="Acme")]
        assert not bluff.overlapping_employment(emp)

    def test_two_roles_at_the_same_real_employer_are_a_promotion(self):
        emp = [_emp("Engineer", "2015", "2020", employer="Meridian"),
               _emp("Senior Engineer", "2018", "2024", employer="Meridian")]
        assert not bluff.overlapping_employment(emp)

    def test_implausibly_long_overlap_is_our_parsing_error_not_their_fraud(self):
        """A 26-year overlap says our date extraction failed. Reporting it as possible
        fabrication would be an accusation built on our own bug."""
        emp = [_emp("A", "1996", "present", employer="Acme"),
               _emp("B", "2000", "present", employer="Globex")]
        assert not bluff.overlapping_employment(emp)

    def test_a_genuine_two_year_overlap_still_flags(self):
        emp = [_emp("A", "2015", "2020", employer="Acme"),
               _emp("B", "2017", "2019", employer="Globex")]
        flags = bluff.overlapping_employment(emp)
        assert flags and "years" in flags[0].description
