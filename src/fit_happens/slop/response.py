"""Checkpoint 3 - the response scan.

This is the checkpoint the brief specified and we stubbed, because it needs something no
recruiter-side tool has: the candidate actually answering. Now that they can, three checks run.

The middle one is the real signal, and it is the only place `check_claims`-style two-document
comparison has ever fitted. Recruiter-side there was no second document to compare a CV
against. Here there is: the answers versus the CV. A date in an answer that contradicts the
employment history is a specific, checkable inconsistency of exactly the kind the corroboration
rule was written for.

The third check is the whiteboard's "style consistency by casual questions", which never had
anywhere to live until now. One question is deliberately informal; how someone writes when
they are not performing becomes the baseline, and a markedly more polished answer elsewhere is
a divergence worth asking about. Worth stating plainly: divergence is not dishonesty. People
write more carefully about things that matter, and someone may reasonably use assistance on a
technical answer and not a casual one.

All the usual rules hold. Flag for human review is the ceiling, two independent flags before
anything is called likely fabricated, and style alone is never enough.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel

from ..fit.derived import career_start_year, parse_when, total_experience_years
from ..schemas import CheckpointResult, Claim, Employment, Flag, Span
from .corroborate import decide
from .knowledge import tech_release_year
from .style import read_style

THIS_YEAR = date.today().year

YEAR_RE = re.compile(r"\b(19[7-9]\d|20[0-2]\d)\b")
DURATION_RE = re.compile(r"\b(\d{1,2}(?:\.\d)?)\s*(?:\+\s*)?(years?|yrs?)\b", re.I)


class Answer(BaseModel):
    question: str
    text: str
    # The casual question exists to capture unguarded writing. Its answer is the baseline the
    # others are compared against, and it is never itself compared to anything.
    is_baseline: bool = False


CASUAL_QUESTION = (
    "Before the specifics - what is a piece of work you enjoyed recently, and what made it "
    "good? A couple of sentences is plenty, no need to polish it."
)


def _flag(pattern_id: str, description: str, quote: str, confidence: float) -> Flag:
    return Flag(pattern_id=pattern_id, description=description,
                span=Span(text=quote[:220]), confidence=confidence)


def check_against_cv(answers: list[Answer], claims: list[Claim],
                     employment: list[Employment]) -> list[Flag]:
    """Deterministic contradictions between what they now say and what the CV said.

    Every check here is arithmetic against dates already extracted for the fit engine, so a
    candidate can verify any of it themselves - which is the standard anything that produces
    a flag has to meet.
    """
    flags: list[Flag] = []
    start_year = career_start_year(employment)
    total_years = total_experience_years(employment)
    ends = [d.year for e in employment if (d := parse_when(e.end) or parse_when(e.start))]
    latest = max(ends) if ends else None

    for a in answers:
        if a.is_baseline or not a.text.strip():
            continue

        for m in DURATION_RE.finditer(a.text):
            claimed = float(m.group(1))
            if total_years and claimed > total_years + 1.5:
                flags.append(_flag(
                    "answer_exceeds_career",
                    f"the answer claims {claimed:.0f} years, but the CV's employment history "
                    f"covers {total_years:.1f} years in total",
                    a.text[max(0, m.start() - 60):m.end() + 60], 0.7))

        for m in YEAR_RE.finditer(a.text):
            year = int(m.group(1))
            if start_year and year < start_year - 1:
                flags.append(_flag(
                    "answer_predates_career",
                    f"the answer refers to {year}, before the earliest role on the CV "
                    f"({start_year})",
                    a.text[max(0, m.start() - 60):m.end() + 60], 0.6))
            if latest and year > max(latest, THIS_YEAR):
                flags.append(_flag(
                    "answer_future_date",
                    f"the answer refers to {year}, which is in the future",
                    a.text[max(0, m.start() - 60):m.end() + 60], 0.5))

        # A technology named with a duration that reaches back before it existed.
        for m in DURATION_RE.finditer(a.text):
            window = a.text[max(0, m.start() - 90):m.end() + 90]
            years = float(m.group(1))
            for token in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", window):
                released = tech_release_year(token)
                if released and THIS_YEAR - years < released - 1:
                    flags.append(_flag(
                        "answer_predates_technology",
                        f"the answer claims {years:.0f} years of {token}, which was released "
                        f"in {released}",
                        window, 0.85))
                    break
    return flags


def check_style_consistency(answers: list[Answer]) -> list[Flag]:
    """Compare the polished answers against the unguarded baseline.

    Explicitly NOT evidence of dishonesty. People write more carefully about things that
    matter, and using assistance on a technical answer but not a casual one is ordinary
    behaviour. This is a prompt to talk to them, at low confidence, and it can never reach a
    flag on its own.
    """
    baseline = next((a for a in answers if a.is_baseline and a.text.split()), None)
    others = [a for a in answers if not a.is_baseline and len(a.text.split()) >= 25]
    if not baseline or not others:
        return []

    base = read_style(baseline.text)
    flags: list[Flag] = []
    for a in others:
        s = read_style(a.text)
        if s.score - base.score > 0.45:
            flags.append(_flag(
                "style_divergence",
                "this answer reads markedly more polished than the candidate's own informal "
                "writing on the same form",
                a.text, 0.3))
    return flags


def scan_responses(answers: list[Answer], claims: list[Claim],
                   employment: list[Employment]) -> CheckpointResult:
    combined = "\n".join(a.text for a in answers if not a.is_baseline)
    style = read_style(combined)

    flags = check_against_cv(answers, claims, employment)
    flags += check_style_consistency(answers)

    result = decide(flags, style)
    return CheckpointResult(checkpoint="cp3_response", verdict=result.verdict,
                            flags=result.flags, reason=result.reason)
