"""Claim shortlisting.

Both tests here exist because of bugs that looked like working code:
  1. `partial_token_set_ratio` saturated at 100, so all 199 claims scored an identical 90.0 and
     the "ranking" was really document order.
  2. Token sets were not singularised, so a claim named "Firewall" scored zero against a
     requirement that says "firewalls".
Each dropped the correct evidence for a requirement that named it explicitly.
"""

from __future__ import annotations

import pytest

from fit_happens.fit.select import dedupe, score_claim, select
from fit_happens.schemas import Claim, Requirement, Span

NETWORK = Requirement(id="r0", text="Network administration experience (routing, switching, firewalls)",
                      kind="required", category="skill")
AD = Requirement(id="r1", text="Hands-on Active Directory administration and design",
                 kind="required", category="skill")


def _c(i: int, skill: str, evidence: str = "") -> Claim:
    return Claim(id=f"c{i}", skill=skill, evidence=Span(text=evidence or skill))


def test_scores_are_not_all_identical():
    """The saturation bug: a metric that returns the same number for everything is worse than
    no metric, because it looks like it is ranking."""
    claims = [_c(0, "Firewall"), _c(1, "MS Office"), _c(2, "routing"), _c(3, "Chef de Partie"),
              _c(4, "Active Directory"), _c(5, "payroll processing")]
    scores = {round(score_claim(c, NETWORK), 1) for c in claims}
    assert len(scores) > 2, f"metric is saturating: {scores}"


@pytest.mark.parametrize("skill", ["Firewall", "firewalls", "Routing", "switching"])
def test_singular_and_plural_both_match(skill):
    """'firewall' must match a requirement that says 'firewalls'."""
    assert score_claim(_c(0, skill), NETWORK) > 60


def test_precise_short_claim_outranks_vague_long_one():
    """A one-word claim can only cover a fraction of a long requirement. Normalising by the
    requirement penalised exactly the claims that were most on-point."""
    precise = score_claim(_c(0, "Firewall"), NETWORK)
    vague = score_claim(_c(1, "general administration experience across systems"), NETWORK)
    assert precise > vague


def test_irrelevant_claims_score_low():
    assert score_claim(_c(0, "Chef de Partie"), NETWORK) < 40
    assert score_claim(_c(1, "payroll processing"), AD) < 40


def test_relevant_claims_survive_selection():
    """The end-to-end property: evidence a requirement names by word must reach the mapper."""
    claims = [_c(i, s) for i, s in enumerate(
        ["Firewall", "routing", "Active Directory", "MS Office", "coffee making", "payroll",
         "Chef de Partie", "flower arranging", "VMware vSphere", "Cisco CCNA"] * 8)]
    chosen = {c.skill.lower() for c in select(claims, [NETWORK, AD], per_requirement=5)}
    assert "firewall" in chosen
    assert "routing" in chosen
    assert "active directory" in chosen


def test_dedupe_removes_restatements_but_keeps_distinct_skills():
    claims = [_c(0, "server administration"), _c(1, "Server Administration"),
              _c(2, "administration of servers"), _c(3, "Active Directory")]
    kept = {c.skill for c in dedupe(claims)}
    assert "Active Directory" in kept
    assert len(kept) < 4


def test_selection_returns_everything_when_there_is_little():
    claims = [_c(0, "Firewall"), _c(1, "routing")]
    assert len(select(claims, [NETWORK], per_requirement=10)) == 2
