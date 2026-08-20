"""Checkpoint 2 - the ID check. Eight patterns; six are pure Python.

Following ki-check's principle verbatim: the decisions come from a rules engine, never the
model. Six of these are arithmetic or lookup - a claim that predates the technology's release
is not a matter of opinion, and the candidate can check it themselves. Only the last two need
judgement, and they are the two that can be wrong.

Every flag names a specific span. A flag with no span is not a flag, it is a feeling.
"""

from __future__ import annotations

import re
from datetime import date

from ..fit.derived import career_start_year, parse_when
from ..schemas import Claim, Employment, Flag, Requirement, Span
from .knowledge import IMPOSSIBLE_CERT_PATTERNS, tech_release_year

THIS_YEAR = date.today().year


def _flag(pattern_id: str, description: str, span: Span, confidence: float) -> Flag:
    return Flag(pattern_id=pattern_id, description=description, span=span, confidence=confidence)


# ---------------------------------------------------------------- 1 & 2: impossible durations


def expertise_predates_technology(claims: list[Claim]) -> list[Flag]:
    """A claim reaching back before the thing existed. The strongest flag we can raise: pure
    arithmetic, no judgement, and checkable by the candidate."""
    out = []
    for c in claims:
        released = tech_release_year(c.skill)
        if not released:
            continue
        start = c.since_year or (THIS_YEAR - int(c.years_claimed) if c.years_claimed else None)
        if start and start < released:
            out.append(_flag(
                "expertise_predates_technology",
                f"{c.skill} is claimed from {start}, but it was not publicly released until "
                f"{released} - {released - start} years earlier than possible",
                c.evidence, 0.9))
    return out


def expertise_predates_career(claims: list[Claim], employment: list[Employment]) -> list[Flag]:
    out = []
    if not (start_year := career_start_year(employment)):
        return out
    for c in claims:
        claimed_from = c.since_year or (THIS_YEAR - int(c.years_claimed) if c.years_claimed else None)
        if claimed_from and claimed_from < start_year - 1:  # 1y grace for study-era use
            out.append(_flag(
                "expertise_predates_career",
                f"{c.skill} is claimed from {claimed_from}, but the earliest role on the resume "
                f"begins in {start_year}",
                c.evidence, 0.6))
    return out


# ---------------------------------------------------------------- 3: overlapping employment


# Employer names that identify nobody. Public resume corpora are anonymised, so every role
# says "Company Name" - and two roles at the same placeholder are not concurrent employment,
# they are two roles whose employers we do not know.
PLACEHOLDER_EMPLOYER = re.compile(
    r"^\s*(company\s*name|company|employer(\s*name)?|organization|organisation|n/?a|"
    r"confidential|undisclosed|various|self|self[- ]employed|freelance|-{1,}|\.{2,})\s*$", re.I)

# Beyond this, an "overlap" is telling us the dates were mis-parsed, not that someone held two
# jobs at once. A 26-year overlap is a data-quality signal, and reporting it as a possible
# fabrication would be an accusation built on our own extraction error.
MAX_CREDIBLE_OVERLAP_MONTHS = 120


def overlapping_employment(employment: list[Employment]) -> list[Flag]:
    """Two full-time roles at once, with no explanation. Contract and advisory work legitimately
    overlaps, so this is a question to ask, not a conclusion - 0.5 confidence, and it needs a
    second independent flag before it can contribute to anything."""
    out = []
    dated = [(e, parse_when(e.start), parse_when(e.end) or date.today()) for e in employment if e.full_time]
    dated = [(e, s, x) for e, s, x in dated if s]
    for i, (a, a_s, a_e) in enumerate(dated):
        for b, b_s, b_e in dated[i + 1:]:
            if PLACEHOLDER_EMPLOYER.match(a.employer or "") or PLACEHOLDER_EMPLOYER.match(b.employer or ""):
                continue
            if (a.employer or "").strip().lower() == (b.employer or "").strip().lower():
                continue  # concurrent roles at ONE employer is a promotion, not a second job
            overlap_days = (min(a_e, b_e) - max(a_s, b_s)).days
            months = overlap_days // 30
            if not (4 < months <= MAX_CREDIBLE_OVERLAP_MONTHS):
                continue  # under 4 months is a handover; over 10 years is our own parsing error
            span = f"{months // 12} years" if months >= 24 else f"{months} months"
            out.append(_flag(
                "overlapping_employment",
                f"{a.title} at {a.employer} and {b.title} at {b.employer} overlap by "
                f"{span}, both listed as full time",
                a.evidence, 0.5))
    return out


# ---------------------------------------------------------------- 4: duplicated bullets


def duplicate_bullets(text: str) -> list[Flag]:
    lines = [" ".join(ln.split()) for ln in text.splitlines()]
    lines = [ln for ln in lines if len(ln.split()) >= 8]
    seen: dict[str, int] = {}
    out = []
    for ln in lines:
        key = re.sub(r"[^a-z0-9 ]", "", ln.lower())
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            out.append(_flag("duplicate_bullet",
                             "the same bullet appears word for word under two different roles",
                             Span(text=ln[:200]), 0.65))
    return out


# ---------------------------------------------------------------- 5: round numbers


def round_number_density(text: str) -> list[Flag]:
    nums = re.findall(r"\b\d{2,}\b%?", text)
    if len(nums) < 6:
        return []
    # "Round" means the final digit is 0 or 5. The first attempt used \d*[05]0%?, which
    # requires the TENS digit to be 0 or 5 - so it matched "50%" and silently missed "30%".
    round_ones = [n for n in nums if re.fullmatch(r"\d*[05]%?", n)]
    ratio = len(round_ones) / len(nums)
    if ratio > 0.8:
        return [_flag("round_numbers",
                      f"{len(round_ones)} of {len(nums)} figures are round numbers ending in 0 or 5 "
                      f"({ratio:.0%}) - measured results are rarely this tidy",
                      Span(text=", ".join(round_ones[:8])), 0.45)]
    return []


# ---------------------------------------------------------------- 6: impossible certifications


def impossible_certification(text: str) -> list[Flag]:
    out = []
    for pattern, why in IMPOSSIBLE_CERT_PATTERNS:
        if m := pattern.search(text):
            out.append(_flag("impossible_certification",
                             f"'{m.group(0)}' is not how that credential is issued - {why}",
                             Span(text=m.group(0)), 0.7))
    return out


# ---------------------------------------------------------------- 7: JD echo


_WORD = re.compile(r"[a-z][a-z'-]+")
GENERIC = {
    "experience", "work", "working", "team", "role", "years", "strong", "ability", "skills",
    "knowledge", "including", "development", "management", "business", "support", "design",
    "using", "within", "across", "high", "quality", "new", "well", "good", "also", "must",
}


def jd_echo(resume_text: str, requirements: list[Requirement], n: int = 6) -> list[Flag]:
    """Phrases lifted near-verbatim from the advert.

    From the whiteboard's goal 2 - "bluff indicator for CVs *overfit on JD*" - which the later
    write-ups softened away. A resume that echoes the advert is describing the job rather than
    the person, and it costs nothing to detect.

    n-grams of 6+ words, ignoring runs made only of generic filler, so "5 years of experience
    in software development" does not fire on every candidate alive.
    """
    jd_text = " ".join(r.text for r in requirements).lower()
    jd_words = _WORD.findall(jd_text)
    jd_grams = {" ".join(jd_words[i:i + n]) for i in range(len(jd_words) - n + 1)}
    if not jd_grams:
        return []

    r_words = _WORD.findall(resume_text.lower())
    hits: list[str] = []
    for i in range(len(r_words) - n + 1):
        gram = " ".join(r_words[i:i + n])
        if gram in jd_grams and sum(1 for w in r_words[i:i + n] if w not in GENERIC) >= 3:
            hits.append(gram)

    merged: list[str] = []
    for h in hits:
        if not merged or h.split()[:-1] != merged[-1].split()[1:]:
            merged.append(h)
        else:
            merged[-1] += " " + h.split()[-1]

    if len(merged) >= 2:
        return [_flag("jd_echo",
                      f"{len(merged)} phrases of {n}+ words appear near-verbatim in both the "
                      f"resume and this job advert",
                      Span(text=" / ".join(m[:80] for m in merged[:3])),
                      min(0.75, 0.3 + 0.12 * len(merged)))]
    return []


# ---------------------------------------------------------------- runner


def run_deterministic(
    text: str,
    claims: list[Claim],
    employment: list[Employment],
    requirements: list[Requirement] | None = None,
) -> list[Flag]:
    """All six rules-engine patterns. No model call, no network, no cost."""
    flags: list[Flag] = []
    flags += expertise_predates_technology(claims)
    flags += expertise_predates_career(claims, employment)
    flags += overlapping_employment(employment)
    flags += duplicate_bullets(text)
    flags += round_number_density(text)
    flags += impossible_certification(text)
    if requirements:
        flags += jd_echo(text, requirements)
    return flags
