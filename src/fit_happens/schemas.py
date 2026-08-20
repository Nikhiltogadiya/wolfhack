"""Core types.

The separation between Fit Engine and Slop Bouncer is enforced *here*, by what each type is
allowed to contain, rather than by discipline at the call sites:

- `Claim` and `Requirement` carry no style, sloppiness or authenticity fields. `score_fit()`
  takes only those two types, so writing quality has no path into the fit number. It is not
  that we choose not to use it - the function cannot see it.
- `Verdict` has no reject member. Slop Bouncer cannot return a rejection because no such value
  exists to return.

Both properties are asserted in tests/test_invariants.py. If you add a field or an enum member
that breaks one, those tests fail, which is the point.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- evidence


class Span(BaseModel):
    """A verbatim pointer back into a source document. Every score traces to one of these."""

    text: str = Field(description="verbatim quoted text, never paraphrased")
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    bbox: tuple[float, float, float, float] | None = None

    def cite(self) -> str:
        if self.line_start and self.line_end:
            return f"Resume line {self.line_start}-{self.line_end}"
        if self.page is not None:
            return f"page {self.page + 1}"
        return "resume"


# ---------------------------------------------------------------- ingest


HideMethod = Literal[
    "tiny_font",
    "solid_color_block",
    "low_variance",
    "phantom_text_no_ink",
    "engine_divergence",
    "zero_width_chars",
]


class HiddenFinding(BaseModel):
    """Text present in the file but not visible to a human reading it."""

    method: HideMethod
    excerpt: str
    span: Span
    provenance: str = Field(description="human-readable why, e.g. 'white fill, page 2, 0.5pt'")
    looks_like_instruction: bool = False


class Document(BaseModel):
    """An ingested resume.

    `text` is the SANITISED text and is the only field any downstream stage may read. Hidden
    spans are stripped from it before it exists, so an injected instruction cannot reach a
    prompt even by accident.
    """

    source_path: str
    text: str
    raw_text: str
    hidden: list[HiddenFinding] = []
    engine_chars: dict[str, int] = {}
    divergence: float | None = None

    @property
    def injection_flagged(self) -> bool:
        return any(h.looks_like_instruction for h in self.hidden)


# ---------------------------------------------------------------- job description


class Requirement(BaseModel):
    id: str
    text: str
    kind: Literal["required", "preferred"]
    category: Literal["skill", "experience", "credential", "eligibility", "domain"]
    dealbreaker: bool = False
    source: Literal["external", "internal"] = "external"


# ---------------------------------------------------------------- claims


class Claim(BaseModel):
    """One thing the resume asserts.

    `years_claimed` and `since_year` are deliberately separate fields. On the very first
    extraction we ran, the model returned years=2019.0 for "Jenkins since 2019" - conflating a
    calendar year with a duration. One float invites that error; two typed fields make it
    impossible to express. Durations are computed downstream in Python, never by the model.
    """

    id: str
    skill: str
    years_claimed: float | None = None
    since_year: int | None = None
    level: str | None = None
    employer: str | None = None
    evidence: Span


class Employment(BaseModel):
    """A dated role. Feeds the deterministic bluff patterns (overlap, expertise predating career)."""

    employer: str
    title: str
    start: str | None = None
    end: str | None = None
    full_time: bool = True
    evidence: Span


# ---------------------------------------------------------------- fit


class Match(BaseModel):
    requirement_id: str
    strength: Literal["strong", "moderate", "weak", "missing"]
    claim_ids: list[str] = []
    rationale: str = ""
    evidence: list[Span] = []


class Gap(BaseModel):
    requirement_id: str
    severity: Literal["critical", "major", "minor"]
    text: str


class FitScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    required_coverage: float
    preferred_coverage: float
    matches: list[Match] = []
    gaps: list[Gap] = []
    dealbreakers_unmet: list[str] = []
    capped_by_dealbreaker: bool = False


# ---------------------------------------------------------------- slop


class Verdict(str, Enum):
    """The complete set of things Slop Bouncer may conclude.

    There is no REJECT. Do not add one - `flag_for_human` is the ceiling by design, and
    tests/test_invariants.py::test_no_reject_path asserts this enum stays exactly this size.
    """

    CLEAR = "clear"
    INCONCLUSIVE = "inconclusive"
    FLAG_FOR_HUMAN = "flag_for_human"


class Flag(BaseModel):
    """One specific, evidenced inconsistency. Never a conclusion on its own."""

    pattern_id: str
    description: str
    span: Span
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class StyleRead(BaseModel):
    """CP1. A spectrum, never a verdict.

    Deliberately NOT a neural AI-text classifier: Liang et al. (Patterns 2023) measured a
    61.22% false-positive rate for non-native English writers across seven detectors, and the
    mechanism is low perplexity, so every perplexity-based detector inherits it. These are
    interpretable pattern hits instead, each with a span.
    """

    score: float = Field(ge=0.0, le=1.0)
    band: Literal["low", "grey", "high"]
    patterns_fired: list[Flag] = []
    word_count: int = 0
    caveat: str = ""


class CheckpointResult(BaseModel):
    checkpoint: Literal["cp1_style", "cp2_claims", "cp3_response"]
    verdict: Verdict
    flags: list[Flag] = []
    reason: str = ""
