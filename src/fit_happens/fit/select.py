"""Pick which claims the mapper actually needs to see.

Chunked extraction is thorough - 303 claims from one resume - and most of them are irrelevant
to any given job advert. Sending all of them costs a ~33k-character prompt, makes the mapper
slow enough to time out, and buries the handful of claims that decide the score.

So: shortlist per requirement with cheap fuzzy matching, then union. Deterministic and free
(rapidfuzz, no model call), and it makes the expensive judgement call cheap to make well.

Deliberately generous - `per_requirement=10` rather than 3. Recall matters far more than
precision here: a claim wrongly included costs a few tokens, while a claim wrongly excluded
cannot be matched at all and silently lowers a real candidate's score.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from ..schemas import Claim, Requirement

# Words that appear in every job requirement and carry no discriminating signal.
STOPWORDS = {
    "experience", "experienced", "with", "and", "or", "the", "a", "an", "of", "in", "on", "for",
    "to", "at", "least", "years", "year", "strong", "solid", "proven", "demonstrated", "hands",
    "ability", "able", "must", "have", "has", "such", "as", "is", "are", "be", "including",
    "e.g", "etc", "our", "you", "your", "we", "will", "would", "plus", "desirable", "preferred",
    "ideally", "familiarity", "knowledge", "understanding", "skills", "work", "working",
}
_TOKEN = re.compile(r"[a-z0-9+#.]{2,}")


def _stem(token: str) -> str:
    """Crude singularisation. Same bug bit the JD guard: 'firewall' never matches 'firewalls',
    so a claim named Firewall scored zero against a requirement that says firewalls."""
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _content_tokens(text: str) -> set[str]:
    return {_stem(t) for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS}

NEAR_DUPLICATE = 92  # token_set_ratio above which two claims say the same thing


def dedupe(claims: list[Claim]) -> list[Claim]:
    """Drop claims that restate one already kept.

    Per-chunk extraction produces "server administration" and "managing servers" from adjacent
    bullets; both are true and only one is useful. Keeps the first, which is also the one whose
    evidence span appears earliest in the document.
    """
    kept: list[Claim] = []
    for c in claims:
        text = f"{c.skill}".lower()
        if not any(fuzz.token_set_ratio(text, f"{k.skill}".lower()) >= NEAR_DUPLICATE for k in kept):
            kept.append(c)
    return kept


def score_claim(claim: Claim, requirement: Requirement) -> float:
    """Relevance of one claim to one requirement, 0-100.

    NOT `partial_token_set_ratio`, which was the first attempt: it returns ~100 for almost any
    pair, so every one of 199 claims scored an identical 90.0 and the "ranking" was really
    document order. Firewall, Cisco and VPN claims were dropped for a requirement that
    literally says "firewalls". A metric that saturates is worse than no metric, because it
    looks like it is working.

    Now: how many of the requirement's content words this claim actually accounts for, with the
    skill name weighted above the surrounding bullet text.
    """
    req_tokens = _content_tokens(requirement.text)
    if not req_tokens:
        return 0.0
    skill_tokens = _content_tokens(claim.skill)
    evidence_tokens = _content_tokens(claim.evidence.text[:400])

    # Normalise by the SMALLER set, not by the requirement. A one-word claim like "Firewall"
    # can only ever cover a fifth of "Network administration (routing, switching, firewalls)",
    # and penalising it for that is backwards: it is a precise hit, not a partial one.
    direct = len(req_tokens & skill_tokens) / max(1, min(len(req_tokens), len(skill_tokens)))
    contextual = len(req_tokens & evidence_tokens) / max(1, min(len(req_tokens), len(evidence_tokens) or 1))
    overlap = 100.0 * min(1.0, direct + 0.4 * contextual)

    # Fuzzy match catches morphology the token sets miss - "firewalls" vs "Firewall",
    # "routing" vs "routers" - but only on the skill name, where it cannot saturate.
    fuzzy = fuzz.token_set_ratio(claim.skill.lower(), requirement.text.lower()) * 0.55
    return max(overlap, fuzzy)


def select(
    claims: list[Claim],
    requirements: list[Requirement],
    per_requirement: int = 10,
    cap: int = 90,
) -> list[Claim]:
    """The claims worth showing the mapper, in document order."""
    claims = dedupe(claims)
    if len(claims) <= per_requirement:
        return claims

    chosen: dict[str, Claim] = {}
    for r in requirements:
        ranked = sorted(claims, key=lambda c: -score_claim(c, r))
        for c in ranked[:per_requirement]:
            chosen[c.id] = c

    ordered = [c for c in claims if c.id in chosen]
    if len(ordered) > cap:
        # Keep the globally most relevant, then restore document order.
        best = sorted(ordered, key=lambda c: -max(score_claim(c, r) for r in requirements))[:cap]
        keep = {c.id for c in best}
        ordered = [c for c in ordered if c.id in keep]
    return ordered
