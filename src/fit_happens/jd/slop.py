"""Run the same scrutiny over the employer's own job advert.

The challenge names this as the candidate's first problem: *"Generic job ads: AI-generated
descriptions blur meaningful differences between roles."* Slop Bouncer already knows how to
read for hollow writing, so pointing it at the advert costs almost nothing and makes the tool
symmetrical - it holds the employer to the standard it holds applicants to.

It also has a practical use beyond the demo. A vague advert produces vague requirements, which
produce weak matches for everybody, so a low clarity score is a warning that the *ranking* is
about to be unreliable - not just that the prose is dull.
"""

from __future__ import annotations

import re

from ..schemas import Flag, Span, StyleRead
from ..slop.style import read_style

# Phrases that fill space in a job advert without telling a candidate anything they could act
# on. Each one has a concrete replacement a hiring manager can actually write.
HOLLOW = {
    r"\brock\s?star\b": "say what the person will build instead",
    r"\bninja\b": "say what the person will build instead",
    r"\bguru\b": "say what the person will build instead",
    r"\bwear(?:s|ing)? many hats\b": "list the actual responsibilities",
    r"\bfast[- ]paced environment\b": "describe the real delivery cadence",
    r"\bwork hard,? play hard\b": "describe the working pattern",
    r"\bcompetitive salary\b": "publish the band",
    r"\bmarket[- ]leading\b": "state the market position",
    r"\bdynamic team\b": "say how big the team is and what it owns",
    r"\bself[- ]starter\b": "say what autonomy the role actually has",
    r"\bhit the ground running\b": "say what onboarding exists",
    r"\bpassionate about\b": "state the requirement plainly",
    r"\bwe are looking for someone who\b": "state the requirement plainly",
    r"\bexcellent communication skills\b": "say who they communicate with and about what",
    r"\bteam player\b": "describe how the team collaborates",
    r"\battention to detail\b": "say what accuracy the work demands",
    r"\bthink outside the box\b": "say what problem needs solving",
    r"\bfamily\b(?=[^.]{0,40}\bteam\b)": "describe the team honestly",
    r"\bunlimited (?:pto|holiday|vacation)\b": "state the actual expected time off",
}

# Things a candidate can act on. Their ABSENCE is the strongest signal an advert is generic -
# far more telling than the presence of any buzzword.
CONCRETE_SIGNALS = {
    "salary or band": r"[€$£]\s?\d{2,3}[.,]?\d{0,3}\s?(k|000)|\b\d{2,3}\s?[-–]\s?\d{2,3}\s?k\b|\bsalary range\b",
    # Spelled-out numbers count. Our own demo advert says "a team of four engineers" and a
    # digits-only pattern reported it as missing - a false negative on the very first real JD.
    "team size": (r"\bteam of (\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"
                  r"|\b(\d+|two|three|four|five|six|seven|eight|nine|ten)[- ]person team\b"
                  r"|\bteam size\b|\bteam of \w+ engineers?\b"),
    "specific tooling": r"\b(kubernetes|terraform|postgres|django|react|kafka|aws|gcp|azure|sap|vmware|active directory)\b",
    "location or remote policy": r"\b(remote|hybrid|on[- ]site|days? (a|per) week in)\b",
    "who they report to": (r"\breport(s|ing)? (in)?to\b|\bworks? (directly )?with the\b"
                           r"|\blead(s|ing)? (a )?team of\b|\bescalation point\b"),
}


def scan_job_ad(text: str) -> tuple[StyleRead, list[Flag], float]:
    """Returns (style read, hollow-phrase flags, clarity 0-1).

    Clarity is driven mostly by what the advert *contains*, not by what it avoids: an advert
    can be entirely free of buzzwords and still tell a candidate nothing.
    """
    style = read_style(text)
    low = text.lower()

    hollow_flags: list[Flag] = []
    for pattern, fix in HOLLOW.items():
        if m := re.search(pattern, low, re.IGNORECASE):
            hollow_flags.append(Flag(
                pattern_id="hollow_phrase",
                description=f"'{m.group(0).strip()}' tells a candidate nothing - {fix}",
                span=Span(text=text[max(0, m.start() - 40):m.end() + 40].strip()),
                confidence=0.4,
            ))

    present = {name for name, pat in CONCRETE_SIGNALS.items() if re.search(pat, low, re.IGNORECASE)}
    missing = sorted(set(CONCRETE_SIGNALS) - present)
    for name in missing:
        hollow_flags.append(Flag(
            pattern_id="missing_specifics",
            description=f"the advert never states {name}",
            span=Span(text=""), confidence=0.3,
        ))

    concreteness = len(present) / len(CONCRETE_SIGNALS)
    hollow_penalty = min(0.4, 0.08 * sum(1 for f in hollow_flags if f.pattern_id == "hollow_phrase"))
    clarity = round(max(0.0, min(1.0, concreteness - hollow_penalty)), 3)
    return style, hollow_flags, clarity
