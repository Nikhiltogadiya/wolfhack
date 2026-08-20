"""Resume text -> typed claims and employment history.

Everything here is *extraction*, never judgement. The model reports what the document says and
quotes it; every number that ends up in a score is computed downstream in Python.

That split is not stylistic. On the first extraction we ever ran, asked for "years" from
"Built CI with Jenkins since 2019", the model returned 2019.0 - a calendar year in a duration
field. So the schema separates `years_claimed` from `since_year` and the arithmetic lives in
score.py, where it can be tested.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from .. import llm
from ..ingest import sanitize
from ..schemas import Claim, Document, Employment, Span


class _Claim(BaseModel):
    skill: str = Field(description="the technology, tool, method or capability claimed")
    years_claimed: float | None = Field(default=None, description="ONLY if the text states a DURATION, e.g. '4 years'. Null otherwise.")
    since_year: int | None = Field(default=None, description="ONLY if the text states a START YEAR, e.g. 'since 2019'. Null otherwise.")
    level: str | None = Field(default=None, description="expert/advanced/proficient/familiar, only if stated")
    employer: str | None = None
    evidence: str = Field(description="the verbatim sentence or bullet this came from")


class _Employment(BaseModel):
    employer: str
    title: str
    start: str | None = Field(default=None, description="YYYY-MM or YYYY as written")
    end: str | None = Field(default=None, description="YYYY-MM, YYYY, or 'present'")
    full_time: bool = True
    evidence: str


class _Extraction(BaseModel):
    claims: list[_Claim]
    employment: list[_Employment]


CHUNK_CHARS = 2200  # measured: see the docstring note on why this is not one big call


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on line boundaries into extractable pieces.

    Not an optimisation - a correctness fix. Asked to extract from a 14,000-character resume in
    one call, the model returned FIVE skills and silently dropped Active Directory, VMware,
    Cisco, SCCM, VPN and Security+, all of which are plainly in the document. It summarised
    instead of enumerating. Per-chunk extraction gets all of them, because no single call is
    ever looking at enough text to be tempted to summarise.
    """
    out: list[str] = []
    current: list[str] = []
    length = 0
    for line in text.splitlines():
        if length + len(line) > size and current:
            out.append("\n".join(current))
            current, length = [], 0
        current.append(line)
        length += len(line) + 1
    if current:
        out.append("\n".join(current))
    return out or [text]


PROMPT = """Extract what this resume CLAIMS. You are a reader, not a judge: do not assess
whether anything is true, impressive, or well written.

Rules:
- A claim is a skill, tool, method or capability the document asserts.
- A skill NAMES a thing: "Active Directory", "VMware", "risk assessment". It is almost always
  one to four words. Do NOT emit duties, sentences or achievements as skills.
  WRONG: skill="managing and maintaining 12 local physical and 20 virtual servers"
  RIGHT: skill="server administration", evidence="Managing and maintaining 12 local physical
         and 20 virtual servers"
  The duty belongs in `evidence`. The name belongs in `skill`.
- years_claimed is a DURATION ("4 years" -> 4). since_year is a START YEAR ("since 2019" ->
  2019). Never put a calendar year in years_claimed. If the text says "since 2019", set
  since_year=2019 and leave years_claimed null.
- evidence must be copied verbatim from the document. Never paraphrase.
- Extract EVERY distinct skill named in the text below. Do not summarise, do not pick
  highlights, do not deduplicate across the section. A dense technical section can easily
  contain fifteen or more. Missing one is a failure; listing one twice is harmless.
- List every employment entry that appears in THIS excerpt, with dates exactly as written.
  If the excerpt contains none, return an empty list.

{resume}"""


def extract_claims(doc: Document) -> tuple[list[Claim], list[Employment]]:
    # doc.text is already sanitised - hidden spans excised - so wrapping is defence in depth
    # rather than the only defence.
    prompts = [
        PROMPT.format(resume=sanitize.wrap_untrusted(chunk, uuid.uuid4().hex[:8], "resume"))
        for chunk in chunk_text(doc.text)
        if chunk.strip()
    ]
    raw_claims: list[_Claim] = []
    raw_emp: list[_Employment] = []
    for ext in llm.structured_many("claim_extract", _Extraction, prompts):
        raw_claims.extend(ext.claims)
        raw_emp.extend(ext.employment)

    claims: list[Claim] = []
    seen_skills: set[str] = set()
    for c in raw_claims:
        key = " ".join(c.skill.lower().split())
        if not key or key in seen_skills:
            continue
        seen_skills.add(key)
        claims.append(
            Claim(
                id=f"c{len(claims)}",
                skill=c.skill.strip(),
                years_claimed=c.years_claimed,
                since_year=c.since_year,
                level=c.level,
                employer=c.employer,
                evidence=_span(c.evidence, doc.text),
            )
        )

    employment: list[Employment] = []
    seen_roles: set[tuple[str, str, str]] = set()
    for e in raw_emp:
        key = (e.employer.lower().strip(), e.title.lower().strip(), str(e.start))
        if key in seen_roles:
            continue
        seen_roles.add(key)
        employment.append(
            Employment(
                employer=e.employer, title=e.title, start=e.start, end=e.end,
                full_time=e.full_time, evidence=_span(e.evidence, doc.text),
            )
        )
    return claims, employment


def _span(quote: str, body: str) -> Span:
    """Locate a quoted line in the document so the UI can cite 'Resume line 56-60'.

    If the model paraphrased instead of quoting, the quote will not be found and we record it
    with no line numbers rather than pointing at the wrong line. A citation that is confidently
    wrong is worse than one that is absent.
    """
    quote = (quote or "").strip()
    lines = body.splitlines()
    needle = " ".join(quote.split()).lower()
    for n, line in enumerate(lines, start=1):
        if needle and needle[:60] in " ".join(line.split()).lower():
            return Span(text=quote, line_start=n, line_end=n)
    return Span(text=quote)
