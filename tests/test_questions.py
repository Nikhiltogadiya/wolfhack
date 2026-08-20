"""Follow-up questions and the job-ad scan."""

from __future__ import annotations

import pytest

from fit_happens.fit.questions import MAX_QUESTIONS, generate
from fit_happens.jd.slop import scan_job_ad
from fit_happens.schemas import FitScore, Flag, Gap, Requirement, Span, Verification

REQS = [
    Requirement(id="r0", text="Must have the right to work in Germany", kind="required",
                category="eligibility", dealbreaker=True),
    Requirement(id="r1", text="Hands-on Active Directory administration", kind="required", category="skill"),
    Requirement(id="r2", text="VMware familiarity", kind="preferred", category="skill"),
]


def _fit(*gaps: Gap) -> FitScore:
    return FitScore(score=0.5, required_coverage=0.5, preferred_coverage=0.5, gaps=list(gaps))


class TestQuestionsAreAskedNotAlleged:
    """Flagging is not a finding of dishonesty. The wording is where that promise is kept or
    quietly broken, so it gets a test."""

    FORBIDDEN = ["discrepanc", "inconsisten", "fabricat", "false", "lying", "dishonest",
                 "suspicious", "concern", "flagged", "misrepresent"]

    def test_gap_questions_are_neutral(self):
        qs = generate(_fit(Gap(requirement_id="r1", severity="major", text="Active Directory")),
                      REQS, polish=False)
        for q in qs:
            assert not any(w in q.question.lower() for w in self.FORBIDDEN), q.question

    def test_flag_questions_are_neutral(self):
        flags = [Flag(pattern_id="expertise_predates_technology", description="d",
                      span=Span(text="10 years of Kubernetes"), confidence=0.9),
                 Flag(pattern_id="overlapping_employment", description="d",
                      span=Span(text="two roles 2018-2020"), confidence=0.5)]
        for q in generate(_fit(), REQS, flags, polish=False):
            assert not any(w in q.question.lower() for w in self.FORBIDDEN), q.question
            assert "?" in q.question


class TestTemplatesAlwaysWork:
    def test_questions_generate_with_the_model_disabled(self):
        """A demo that blanks because an API call failed is not a demo."""
        qs = generate(_fit(Gap(requirement_id="r1", severity="major", text="Active Directory")),
                      REQS, polish=False)
        assert qs and qs[0].question.strip().endswith("?")

    def test_polish_failure_leaves_templates_intact(self, monkeypatch):
        import fit_happens.fit.questions as m

        def boom(*a, **k):
            raise RuntimeError("provider down")

        monkeypatch.setattr(m.llm, "structured", boom)
        qs = generate(_fit(Gap(requirement_id="r1", severity="major", text="Active Directory")),
                      REQS, polish=True)
        assert qs and "Active Directory" in qs[0].question


def test_critical_gaps_come_first():
    fit = _fit(Gap(requirement_id="r2", severity="minor", text="VMware"),
               Gap(requirement_id="r1", severity="major", text="Active Directory"),
               Gap(requirement_id="r0", severity="critical", text="right to work in Germany",
                   needs_confirmation=True))
    assert [q.severity for q in generate(fit, REQS, polish=False)] == ["critical", "major", "minor"]


def test_unstated_hard_gate_becomes_a_confirmation_not_an_accusation():
    fit = _fit(Gap(requirement_id="r0", severity="critical", text="right to work in Germany",
                   needs_confirmation=True))
    q = generate(fit, REQS, polish=False)[0]
    assert q.source == "confirmation"
    assert "does not address" in q.reason


def test_undersold_evidence_produces_a_friendly_question():
    v = [Verification(claim_id="", skill="Docker", state="undersold", note="9 public repos")]
    q = next(q for q in generate(_fit(), REQS, None, v, polish=False) if q.source == "undersold")
    assert "would you like to tell us" in q.question.lower()


def test_question_count_is_bounded():
    gaps = [Gap(requirement_id="r1", severity="major", text=f"skill {i}") for i in range(20)]
    assert len(generate(_fit(*gaps), REQS, polish=False)) <= MAX_QUESTIONS


class TestJobAdScan:
    def test_generic_advert_scores_badly(self):
        generic = ("We want a rockstar ninja who is passionate about technology, a self-starter "
                   "and team player with excellent communication skills who can wear many hats "
                   "in a fast-paced environment. Competitive salary, unlimited PTO, dynamic team.")
        _, flags, clarity = scan_job_ad(generic)
        assert clarity < 0.2
        assert sum(1 for f in flags if f.pattern_id == "hollow_phrase") >= 5

    def test_specific_advert_scores_well(self):
        specific = ("IT Infrastructure Manager, Berlin, three days a week on site. You will lead "
                    "a team of four engineers and report into the CTO. Stack is Active Directory, "
                    "VMware and Terraform. Salary range 85-105k EUR.")
        _, flags, clarity = scan_job_ad(specific)
        assert clarity > 0.7
        assert not [f for f in flags if f.pattern_id == "hollow_phrase"]

    @pytest.mark.parametrize("phrasing", ["a team of four engineers", "team of 4", "6-person team"])
    def test_team_size_is_detected_however_it_is_written(self, phrasing):
        """Our own demo advert says 'a team of four engineers' and a digits-only pattern
        reported it as missing - a false negative on the first real JD we tried."""
        _, flags, _ = scan_job_ad(f"You will lead {phrasing} in Berlin.")
        assert not [f for f in flags if "team size" in f.description]

    def test_our_own_demo_jd_is_specific(self):
        _, flags, clarity = scan_job_ad(open("data/demo/jd_external.md").read())
        assert clarity >= 0.7
        assert not [f for f in flags if f.pattern_id == "hollow_phrase"]


@pytest.mark.parametrize("requirement,forbidden", [
    ("Must have the right to work in Germany", "requires Must"),
    ("You must be legally entitled to work in the EU", "requires You must"),
    ("Must hold a valid security clearance", "requires Must"),
    ("Should have a bachelor's degree", "requires Should"),
])
def test_templates_read_as_english_not_as_concatenation(requirement, forbidden):
    """Job adverts phrase requirements as commands. Dropping one straight into a sentence gives
    'The role requires Must have the right to work in Germany'. The template must stand on its
    own, because the model polish that would smooth it over is the part we cannot depend on."""
    reqs = [Requirement(id="r0", text=requirement, kind="required", category="eligibility",
                        dealbreaker=True)]
    fit = _fit(Gap(requirement_id="r0", severity="critical", text=requirement, needs_confirmation=True))
    q = generate(fit, reqs, polish=False)[0].question
    assert forbidden not in q, q
    assert q.count("  ") == 0
