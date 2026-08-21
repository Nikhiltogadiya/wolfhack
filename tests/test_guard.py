"""The internal-JD guard.

Table-driven on purpose: this is the part a judge will push on, and the answer needs to be
"here is the table, run it" rather than a description of intent.
"""

from __future__ import annotations

import pytest

from fit_happens.jd.guard import ALLOWED_FIELDS, check_value
from fit_happens.jd.model import InternalConstraint, JobDescription

# Legitimate operational constraints. Blocking these would make the feature useless.
SHOULD_ALLOW = [
    ("start_availability", "must be able to start within three weeks"),
    ("start_availability", "backfill for a Q4 departure, latest start 1 November"),
    ("seniority_band", "pitched at senior, not staff - we already have two staff engineers"),
    ("budget_band", "85-105k EUR, hard ceiling"),
    ("mentoring_capacity", "the team is junior so this hire has to mentor two graduates"),
    ("onsite_days", "three days a week in the Berlin office, non-negotiable"),
    ("team_context", "team of six, no dedicated SRE, so on-call is shared"),
    ("tooling", "we actually run GCP and Terraform, the advert says 'cloud'"),
    ("travel_requirement", "roughly one week per quarter to the Munich site"),
    ("language_requirement", "C1 German - the customer base is German-speaking"),
    ("language_requirement", "working language is English; German is genuinely optional"),
    ("security_clearance", "role legally requires a national security clearance"),
    ("shift_pattern", "one week of on-call in five"),
]

# Each must be refused, and the reason must name the right category.
SHOULD_BLOCK = [
    ("seniority_band", "looking for a recent graduate only", "age"),
    ("team_context", "young energetic team, digital natives", "age"),
    ("seniority_band", "no one over 45", "age"),
    ("team_context", "prefer a male candidate for site work", "sex_gender"),
    ("team_context", "she should be comfortable with the lads", "sex_gender"),
    ("team_context", "not planning a family in the next two years", "pregnancy_family"),
    ("language_requirement", "native English speakers only", "race_ethnicity_origin"),
    ("language_requirement", "mother-tongue German", "race_ethnicity_origin"),
    ("team_context", "no visa holders", "race_ethnicity_origin"),
    ("team_context", "must be comfortable with our Christian values", "religion_belief"),
    ("shift_pattern", "must be able-bodied to lift equipment", "disability_health"),
    ("team_context", "no unexplained career gaps", "socioeconomic_proxy"),
    ("team_context", "someone who is a good culture fit", "socioeconomic_proxy"),
    ("seniority_band", "Oxbridge only", "socioeconomic_proxy"),
    ("team_context", "photo required with application", "appearance"),
    ("team_context", "no union members", "union_political"),
    ("team_context", "single, no dependents preferred", "marital_status"),
]


@pytest.mark.parametrize("field_name,value", SHOULD_ALLOW)
def test_operational_constraints_are_allowed(field_name, value):
    r = check_value(field_name, value)
    assert r.allowed, f"wrongly blocked: {value!r} -> {r.reason}"


@pytest.mark.parametrize("field_name,value,category", SHOULD_BLOCK)
def test_protected_characteristics_are_blocked(field_name, value, category):
    r = check_value(field_name, value)
    assert not r.allowed, f"wrongly allowed: {value!r}"
    assert category in {c for c, _ in r.violations}, f"{value!r} blocked, but not as {category}: {r.violations}"


def test_field_outside_the_allowlist_is_refused():
    """The schema is the first line of defence: an unlisted constraint type cannot be expressed."""
    r = check_value("vibe", "someone we would enjoy a beer with")
    assert not r.allowed
    assert "not an allowed constraint type" in r.reason


def test_allowlist_is_small_and_operational():
    assert len(ALLOWED_FIELDS) <= 15, "an allowlist that grows without limit is a free-text box"


def test_blocked_constraint_never_reaches_the_scorer():
    """The load-bearing property: refused input must not influence any score, and must be logged."""
    jd = JobDescription(
        title="Senior Platform Engineer",
        external_text="We are hiring a platform engineer.",
        internal=[
            InternalConstraint(field_name="onsite_days", value="three days in Berlin"),
            InternalConstraint(field_name="team_context", value="young energetic team, no career gaps"),
            InternalConstraint(field_name="mentoring_capacity", value="must mentor two graduates"),
        ],
    )
    reqs = jd.internal_requirements()
    texts = " ".join(r.text for r in reqs).lower()
    assert "young" not in texts and "career gaps" not in texts
    assert len(reqs) == 2
    assert jd.blocked_count() == 1
    refusal = [e for e in jd.audit if e.event == "internal_constraint_REFUSED"]
    assert refusal and "age" in refusal[0].detail


def test_refusals_are_logged_not_silently_dropped():
    jd = JobDescription(
        title="X", external_text="y",
        internal=[InternalConstraint(field_name="team_context", value="Oxbridge only")],
    )
    assert jd.internal_requirements() == []
    assert jd.blocked_count() == 1
    assert "socioeconomic" in jd.audit[0].detail


# Inflections and plurals. A stem followed by \b silently fails on all of these while still
# matching the singular you happened to test, so each gets its own case.
INFLECTIONS = [
    ("team_context", "no union members", "union_political"),
    ("team_context", "candidate must not be pregnant", "pregnancy_family"),
    ("team_context", "no disability accommodations available", "disability_health"),
    ("team_context", "no unexplained career gaps", "socioeconomic_proxy"),
    ("team_context", "without employment gaps", "socioeconomic_proxy"),
    ("seniority_band", "millennials preferred", "age"),
    ("team_context", "prefers candidates from good neighbourhoods", "socioeconomic_proxy"),
    ("language_requirement", "native speakers required", "race_ethnicity_origin"),
    ("team_context", "religious observance may be an issue", "religion_belief"),
    ("team_context", "single, no dependents", "marital_status"),
]


@pytest.mark.parametrize("field_name,value,category", INFLECTIONS)
def test_stems_match_their_inflections(field_name, value, category):
    r = check_value(field_name, value)
    assert not r.allowed, f"inflection escaped the guard: {value!r}"
    assert category in {c for c, _ in r.violations}, f"{value!r}: got {r.violations}"


# --- hard gates -------------------------------------------------------------
# Job adverts phrase work authorisation half a dozen ways. An earlier pattern caught "right to
# work" and "work authorisation" and missed "eligible to work" - which is most real adverts.
# A missed hard gate does not cap the score and never generates a confirmation question, so
# the candidate is never asked about the one thing that could rule them out.

HARD_GATES = [
    "Must have the right to work in Germany",
    "Must be eligible to work in the EU",
    "You must be legally authorised to work in the US",
    "Applicants must be legally entitled to work in Canada",
    "Work authorisation required",
    "Requires a valid work permit",
    "We are unable to offer visa sponsorship",
    "Must hold a valid security clearance",
    "Bachelor's degree required",
    "Must hold a CISSP certification",
    "Must be a registered nurse",
    "Chartered engineer status required",
    "Must hold a CISSP",
    "Candidates must possess a valid driving licence",
    "You need to hold an active SC clearance",
]

NOT_GATES = [
    "Experience with Kubernetes in production",
    "Strong communication skills",
    "Comfortable working across several teams",
    "Familiarity with Terraform is a plus",
    "You will work closely with the platform team",
]


@pytest.mark.parametrize("text", HARD_GATES)
def test_hard_gates_are_detected(text):
    from fit_happens.jd.parse import DEALBREAKER_CUES
    assert DEALBREAKER_CUES.search(text), f"missed a hard gate: {text!r}"


@pytest.mark.parametrize("text", NOT_GATES)
def test_ordinary_requirements_are_not_hard_gates(text):
    from fit_happens.jd.parse import DEALBREAKER_CUES
    assert not DEALBREAKER_CUES.search(text), f"wrongly a hard gate: {text!r}"
