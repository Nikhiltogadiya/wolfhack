"""The rule that decides what a set of flags is allowed to mean.

House rule, from the brief: *"It takes two or more independent, specific inconsistencies
before Slop Bouncer calls something likely fabricated - and it always names which ones."*

"Independent" is doing the work, and it is enforced structurally rather than by counting:
two flags count as corroborating only if they have **different pattern ids** AND point at
**different spans**. Otherwise one oddity that happens to trip three rules, or one rule that
fires three times on the same line, would masquerade as a pattern of dishonesty. That is
precisely the failure mode that ruins someone's application over a typo.

Style never contributes. A document can score 1.0 on every stylistic signal and still come out
`inconclusive`, because writing style is not evidence of fabrication - it is evidence of how
someone writes, which is a different question and one with a documented 61% false-positive rate
for non-native speakers.
"""

from __future__ import annotations

from .. import config
from ..schemas import (
    STYLE_ONLY_PATTERNS, CheckpointResult, Flag, StyleRead, Verdict)

STYLE_ONLY = STYLE_ONLY_PATTERNS  # one definition, in schemas

# The one carve-out from the two-flag rule, and it is a narrow one.
#
# Corroboration exists because every other pattern is an INFERENCE about a claim: a date looks
# odd, a number looks too round, a credential is worded unusually. Any single inference can be
# wrong, so we require two before saying anything.
#
# Hidden text is not an inference. It is an observation about the file: instruction-like text
# was placed where a human reader cannot see it, and either it is there or it is not. Nobody
# does that by accident, and no second signal makes it more or less true. Requiring
# corroboration here would mean silently accepting a document we have already caught being
# manipulated.
#
# Note what this still does NOT do: it flags for human review, exactly like everything else.
# It is not a rejection and it is not a claim that anything on the resume is false.
SELF_SUFFICIENT = {"hidden_text"}


def independent(flags: list[Flag]) -> list[Flag]:
    """The subset that corroborate one another: distinct pattern, distinct evidence."""
    seen_patterns: set[str] = set()
    seen_spans: set[str] = set()
    out: list[Flag] = []
    for f in sorted(flags, key=lambda f: -f.confidence):
        if f.pattern_id in STYLE_ONLY:
            continue
        span_key = " ".join(f.span.text.lower().split())[:120]
        if f.pattern_id in seen_patterns or span_key in seen_spans:
            continue
        seen_patterns.add(f.pattern_id)
        seen_spans.add(span_key)
        out.append(f)
    return out


def decide(flags: list[Flag], style: StyleRead | None = None) -> CheckpointResult:
    corroborating = independent(flags)
    all_flags = list(flags) + list(style.patterns_fired if style else [])

    standalone = [f for f in corroborating if f.pattern_id in SELF_SUFFICIENT]
    if standalone:
        named = "; ".join(f"{f.description} ({f.span.cite()})" for f in standalone)
        return CheckpointResult(
            checkpoint="cp2_claims", verdict=Verdict.FLAG_FOR_HUMAN, flags=all_flags,
            reason=(f"Content was concealed inside the document: {named}. This is an observation "
                    f"about the file rather than an inference about any claim, so it does not "
                    f"need corroborating. Flagged for a person to read - it is not a finding "
                    f"that anything on the resume is false, and it is not a rejection."),
        )

    if len(corroborating) >= config.MIN_INDEPENDENT_FLAGS:
        named = "; ".join(f"{f.pattern_id} ({f.span.cite()})" for f in corroborating)
        return CheckpointResult(
            checkpoint="cp2_claims", verdict=Verdict.FLAG_FOR_HUMAN, flags=all_flags,
            reason=(f"{len(corroborating)} independent inconsistencies, each pointing at a "
                    f"different line: {named}. Flagged for a person to read - this is not a "
                    f"finding of dishonesty and it is not a rejection."),
        )

    if corroborating or (style and style.band != "low"):
        bits = []
        if corroborating:
            bits.append(f"one unconfirmed inconsistency ({corroborating[0].pattern_id})")
        if style and style.band != "low":
            bits.append(f"writing style reads {style.band}")
        return CheckpointResult(
            checkpoint="cp2_claims", verdict=Verdict.INCONCLUSIVE, flags=all_flags,
            reason=(f"{' and '.join(bits)}. Not enough to corroborate: it takes two independent, "
                    f"specific inconsistencies before anything is called likely fabricated."),
        )

    return CheckpointResult(checkpoint="cp2_claims", verdict=Verdict.CLEAR, flags=all_flags,
                            reason="no authenticity inconsistencies found")
