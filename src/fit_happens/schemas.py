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
    # Why a requirement is unmet matters more than that it is unmet:
    #   evidenced    - the resume speaks to this, to some degree
    #   unstated     - the resume is simply silent. NOT evidence of absence.
    #   contradicted - the resume actively indicates the candidate does not have it
    # Only `contradicted` may cap a score. Most resumes never mention work authorisation or
    # clearance, and capping on silence would penalise almost everyone for a question we have
    # not asked them yet. Silence generates a follow-up question instead.
    basis: Literal["evidenced", "unstated", "contradicted"] = "evidenced"
    claim_ids: list[str] = []
    rationale: str = ""
    evidence: list[Span] = []


class Gap(BaseModel):
    requirement_id: str
    severity: Literal["critical", "major", "minor"]
    text: str
    # A gap that exists only because the resume is silent. Seeds a follow-up question and is
    # shown to the recruiter as "needs confirming", never as a deficiency.
    needs_confirmation: bool = False


class FitScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    required_coverage: float
    preferred_coverage: float
    matches: list[Match] = []
    gaps: list[Gap] = []
    dealbreakers_unmet: list[str] = []
    dealbreakers_unstated: list[str] = []
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


# ---------------------------------------------------------------- external verification


class ExternalEvidence(BaseModel):
    """Something observed outside the resume - a repo, a language, a commit history."""

    source: Literal["github"] = "github"
    name: str
    detail: str = ""
    first_seen_year: int | None = None
    last_seen_year: int | None = None
    url: str = ""
    volume: int = 0


class Verification(BaseModel):
    """How one claim stands up against evidence found outside the document.

    `unsupported` is NOT an accusation. Most work is not public: closed-source employers,
    NDAs, non-engineering roles, and anyone who simply does not publish. It means only that
    this particular external source had nothing to say.
    """

    claim_id: str
    skill: str
    state: Literal["corroborated", "unsupported", "undersold"]
    evidence: list[ExternalEvidence] = []
    note: str = ""


class ExternalProfile(BaseModel):
    handle: str = ""
    found: bool = False
    public_repos: int = 0
    evidence: list[ExternalEvidence] = []
    error: str = ""

    @property
    def usable(self) -> bool:
        return self.found and bool(self.evidence)


class CheckpointResult(BaseModel):
    checkpoint: Literal["cp1_style", "cp2_claims", "cp3_response"]
    verdict: Verdict
    flags: list[Flag] = []
    reason: str = ""


# ---------------------------------------------------------------- the assembled result


class CandidateResult(BaseModel):
    """Everything the dashboard shows about one candidate, for one role.

    Note what is NOT here: a blended overall number. The four scores stay four scores. There is
    deliberately no field that combines them, because the moment one exists someone will sort
    by it and the separation the whole product rests on becomes decorative.
    """

    candidate_id: str
    name: str = ""
    category: str = ""
    source_path: str = ""

    # 1. fit
    fit: FitScore
    # 2. resume sloppiness
    style: StyleRead
    # 3. claim consistency (CV bluff risk)
    cp2: CheckpointResult
    # 4. response authenticity - stubbed for the hackathon, shown as "pending"
    cp3_pending: bool = True

    document: Document
    claims: list[Claim] = []
    employment: list[Employment] = []
    verifications: list[Verification] = []
    credentials: list[Verification] = []
    # Recency/completeness of the DOCUMENT. Advisory only - a career break, caring,
    # illness or a layoff all produce an old end date and none is a reason to rank lower.
    freshness_label: str = "UNDATED"
    freshness_note: str = ""
    freshness_tone: str = "grey"
    last_active_year: int | None = None
    questions: list[dict] = []
    audit: list[dict] = []

    @property
    def display_name(self) -> str:
        return self.name.replace("_", " ").replace("-", " ").title()

    @property
    def display_initials(self) -> str:
        parts = [p for p in self.name.replace("_", " ").replace("-", " ").split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or self.name[:2].upper()

    @property
    def authenticity_flags(self) -> list[Flag]:
        """Flags about whether claims hold up. Style patterns are excluded by design."""
        style_only = {"stock_phrases", "self_significance", "negative_parallelism",
                      "copula_avoidance", "uniform_rhythm", "rule_of_three", "em_dash_density"}
        return [f for f in self.cp2.flags if f.pattern_id not in style_only]

    @property
    def bluff_label(self) -> str:
        """The dashboard label, mapped straight from the verdict.

        Derived from the VERDICT, not from a flag count. An earlier version counted flags and
        could label a candidate with two uncorroborated oddities "LIKELY GENUINE" while
        labelling one with none "NOT FLAGGED" - which is backwards, and would have been read
        by a recruiter as a judgement we never made.
        """
        n = len(self.authenticity_flags)
        if self.cp2.verdict == Verdict.FLAG_FOR_HUMAN:
            return f"{n} FLAG" if n == 1 else f"{n} FLAGS"
        if self.cp2.verdict == Verdict.INCONCLUSIVE:
            return "NOT CORROBORATED"
        return "LIKELY GENUINE"

    @property
    def style_label(self) -> str:
        return {"low": "LOW", "grey": "MEDIUM", "high": "HIGH"}[self.style.band]

    @property
    def risk_tone(self) -> str:
        """green / amber / red, for the dashboard pill. Drives colour only, never ranking."""
        if self.cp2.verdict == Verdict.FLAG_FOR_HUMAN:
            return "red"
        if self.cp2.verdict == Verdict.INCONCLUSIVE or self.style.band != "low":
            return "amber"
        return "green"
