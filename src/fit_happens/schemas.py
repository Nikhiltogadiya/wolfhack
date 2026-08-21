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

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- evidence


# Patterns that describe HOW something is written rather than WHETHER it is true. They may
# never contribute to a fabrication verdict - hard rules 2, 3 and 9.
#
# This lived in four places: here, slop/corroborate.py, web/app.py and candidate.html. Three
# of the four were meant to hold the same eight ids and two of them had already drifted to
# seven, silently dropping `style_divergence`. A comment saying "keep these in sync" would
# have documented the trap rather than removed it, so there is now one set and the others
# import it. The template dropped its copy entirely: it wanted CandidateResult's
# `authenticity_flags`, which already applies exactly this filter.
STYLE_ONLY_PATTERNS = frozenset({
    "stock_phrases", "self_significance", "negative_parallelism", "copula_avoidance",
    "uniform_rhythm", "rule_of_three", "em_dash_density", "style_divergence",
})


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

    `source_scope` records WHICH consent scope produced this. Without it, withdrawing consent
    cannot remove the right rows and "you can withdraw" would be a claim we could not honour.

    `unsupported` is NOT an accusation. Most work is not public: closed-source employers,
    NDAs, non-engineering roles, and anyone who simply does not publish. It means only that
    this particular external source had nothing to say.
    """

    claim_id: str
    skill: str
    state: Literal["corroborated", "unsupported", "undersold"]
    evidence: list[ExternalEvidence] = []
    note: str = ""
    source_scope: Literal["cv", "github", "publications"] = "cv"


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
    # 4. response authenticity - computed at render time from the candidate's answers, since
    # those arrive long after the pipeline ran. "Pending" until they reply.
    cp3_pending: bool = True

    document: Document
    claims: list[Claim] = []
    employment: list[Employment] = []
    verifications: list[Verification] = []
    credentials: list[Verification] = []
    # What the candidate allowed us to look at. Shown to the RECRUITER too, so a declined
    # scope reads as a decision the candidate made rather than as missing evidence.
    consent_summary: str = "the CV you sent us"
    consent_grants: dict[str, bool] = {}
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
        """What a recruiter reads.

        `name` holds whatever we know: the name someone typed when applying, or - for a CV
        added straight from the dashboard - the filename. Two things had leaked into the UI:
        the id hash ("Naledi Dube 7B4F54") and bare filenames ("15118506").
        """
        raw = (self.name or self.candidate_id).strip()
        parts = [p for p in re.split(r"[\s_-]+", raw) if p]
        # drop a trailing id hash: short, and not word-like
        if len(parts) > 1 and re.fullmatch(r"[0-9a-f]{4,8}", parts[-1].lower()):
            parts = parts[:-1]
        if not parts or all(p.isdigit() for p in parts):
            return f"Applicant {raw}"
        return " ".join(p if p.isupper() else p.capitalize() for p in parts)

    @property
    def display_initials(self) -> str:
        parts = [p for p in self.display_name.split() if p and p[0].isalpha()]
        return "".join(p[0].upper() for p in parts[:2]) or "?"

    @property
    def external_findings(self) -> list["Verification"]:
        """The external evidence worth showing: what was corroborated, and what the CV left out.

        `unsupported` deliberately excluded. github.verify_claims already documents why it
        returns nothing when there is no profile - "no information must produce no
        verifications rather than a page of `unsupported` rows that read as suspicion" - but
        when a profile DID exist it emitted one such row per unmatched claim. An
        infrastructure candidate produced 24 of them against 1 corroborated finding, and the
        page rendered the first 8, so a recruiter saw eight lines of "no public repository
        evidence" and never saw the one positive result at all. Absence of public code is
        absence of information (hard rule 5); it is not an item of evidence, so it does not
        belong in a list headed External evidence.
        """
        rank = {"corroborated": 0, "undersold": 1}
        found = [v for v in self.verifications if v.state in rank]
        return sorted(found, key=lambda v: rank[v.state])

    @property
    def external_unsupported(self) -> int:
        """How many claims the external source simply had nothing to say about."""
        return sum(1 for v in self.verifications if v.state == "unsupported")

    @property
    def authenticity_flags(self) -> list[Flag]:
        """Flags about whether claims hold up. Style patterns are excluded by design."""
        return [f for f in self.cp2.flags if f.pattern_id not in STYLE_ONLY_PATTERNS]

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
