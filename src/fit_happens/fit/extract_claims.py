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


PROMPT = """Extract what this resume CLAIMS. You are a reader, not a judge: do not assess
whether anything is true, impressive, or well written.

Rules:
- A claim is a skill, tool, method or capability the document asserts.
- Do NOT emit job titles, duties or responsibilities as skills. "Led platform team" is not a
  skill; "Kubernetes" is.
- years_claimed is a DURATION ("4 years" -> 4). since_year is a START YEAR ("since 2019" ->
  2019). Never put a calendar year in years_claimed. If the text says "since 2019", set
  since_year=2019 and leave years_claimed null.
- evidence must be copied verbatim from the document. Never paraphrase.
- List every distinct employment entry with its dates exactly as written.

{resume}"""


def extract_claims(doc: Document) -> tuple[list[Claim], list[Employment]]:
    nonce = uuid.uuid4().hex[:8]
    # doc.text is already sanitised - hidden spans excised - so this is defence in depth
    # rather than the only defence.
    body = sanitize.wrap_untrusted(doc.text, nonce, "resume")
    ext = llm.structured("claim_extract", _Extraction, PROMPT.format(resume=body))

    claims = [
        Claim(
            id=f"c{i}",
            skill=c.skill.strip(),
            years_claimed=c.years_claimed,
            since_year=c.since_year,
            level=c.level,
            employer=c.employer,
            evidence=_span(c.evidence, doc.text),
        )
        for i, c in enumerate(ext.claims)
    ]
    employment = [
        Employment(
            employer=e.employer, title=e.title, start=e.start, end=e.end,
            full_time=e.full_time, evidence=_span(e.evidence, doc.text),
        )
        for e in ext.employment
    ]
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
