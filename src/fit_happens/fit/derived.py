"""Facts computed from employment history, in Python, never asked of the model.

Requirements like "at least 5 years of experience" and "experience leading a team" are
evidenced by the shape of someone's career, not by a skill keyword. Before this existed the
mapper only ever saw skill claims, so a candidate with sixteen years across five roles was
scored as having no evidence of experience at all.

Everything here is deterministic. The model's only job was to copy the date strings out of the
document verbatim; the arithmetic happens here, where it can be tested - which is also the
guard against the very first failure we saw, where "since 2019" came back as years=2019.0.
"""

from __future__ import annotations

import re
from datetime import date

from ..schemas import Employment

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})

# Titles that evidence responsibility for people or a function. Deliberately excludes
# "Manager" inside a product name ("Configuration Manager", "Call Manager"), which is why the
# match is anchored to word boundaries and checked against the title only, never the bullets.
LEADERSHIP_TITLE = re.compile(
    r"\b(manager|lead|leader|head\s+of|director|supervisor|chief|principal|"
    r"vp|vice\s+president|foreman|team\s+lead)\b", re.IGNORECASE)
# Words that look like leadership but are not. Two families, both taken from real corpus titles:
#   - "<noun> Manager" is usually a product (Configuration Manager, Call Manager).
#   - "<noun> Management" is usually a discipline or system, not a report line. "Network
#     Management System Engineer" is a real title from this corpus and that person manages
#     no one. Bare "management" was in the leadership list and matched it.
NOT_LEADERSHIP = re.compile(
    r"\b(configuration|call|network|system|service|patch|package|session|device|asset|"
    r"password|endpoint|database|content|document|incident|change)\s+manager\b"
    r"|\b\w+\s+management\b", re.IGNORECASE)


def parse_when(text: str | None) -> date | None:
    """Parse the date formats resumes actually use. Returns None rather than guessing."""
    if not text:
        return None
    t = text.strip().lower()
    if t in {"present", "current", "now", "to date", "ongoing"}:
        return date.today()
    if m := re.match(r"^(\d{4})[-/](\d{1,2})$", t):
        return date(int(m.group(1)), min(int(m.group(2)), 12), 1)
    if m := re.match(r"^(\d{1,2})[-/](\d{4})$", t):
        return date(int(m.group(2)), min(int(m.group(1)), 12), 1)
    if m := re.match(r"^([a-z]+)\.?\s+(\d{4})$", t):
        if (mon := MONTHS.get(m.group(1)[:3])) or MONTHS.get(m.group(1)):
            return date(int(m.group(2)), mon or MONTHS[m.group(1)], 1)
    if m := re.search(r"\b(19|20)\d{2}\b", t):
        return date(int(m.group(0)), 1, 1)
    return None


def span_months(e: Employment) -> int:
    start, end = parse_when(e.start), parse_when(e.end) or date.today()
    if not start or end < start:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month)


def total_experience_years(employment: list[Employment]) -> float:
    """Union of employment intervals, so overlapping roles are not double-counted.

    Counting each role separately would reward exactly the pattern the bluff detector treats as
    suspicious - two full-time jobs on the same dates.
    """
    intervals = []
    for e in employment:
        s = parse_when(e.start)
        if not s:
            continue
        intervals.append((s, parse_when(e.end) or date.today()))
    if not intervals:
        return 0.0
    intervals.sort()
    merged = [list(intervals[0])]
    for s, x in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], x)
        else:
            merged.append([s, x])
    days = sum((b - a).days for a, b in merged)
    return round(days / 365.25, 1)


def career_start_year(employment: list[Employment]) -> int | None:
    years = [d.year for e in employment if (d := parse_when(e.start))]
    return min(years) if years else None


def leadership_roles(employment: list[Employment]) -> list[Employment]:
    return [
        e for e in employment
        if LEADERSHIP_TITLE.search(e.title or "") and not NOT_LEADERSHIP.search(e.title or "")
    ]


def summarise(employment: list[Employment]) -> str:
    """A computed-facts block for the mapper prompt. Facts, explicitly not claims."""
    if not employment:
        return "(no employment history extracted)"
    years = total_experience_years(employment)
    start = career_start_year(employment)
    leads = leadership_roles(employment)
    lines = [
        f"Total experience (overlaps merged): {years} years"
        + (f", career began {start}" if start else ""),
        f"Roles with a leadership title: {len(leads)}"
        + (f" ({', '.join(e.title for e in leads[:3])})" if leads else " (none)"),
        "Employment history:",
    ]
    for e in employment:
        m = span_months(e)
        dur = f"{m // 12}y {m % 12}m" if m else "duration unclear"
        lines.append(f"  - {e.title} at {e.employer} | {e.start or '?'} to {e.end or '?'} ({dur})")
    return "\n".join(lines)
