"""Map claims onto requirements.

The anti-conflation rules below are lifted from ai-CV-cover-letter's match_scorer, where they
were learned the hard way: without them a model happily accepts vector-database experience as
evidence of graph-database work, or RAG pipeline work as evidence of RAGAs.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from .. import llm
from ..ingest import sanitize
from ..schemas import Claim, Employment, Match, Requirement
from . import derived, select as selector


class _Match(BaseModel):
    requirement_id: str
    strength: str = Field(description="strong | moderate | weak | missing")
    basis: str = Field(default="evidenced", description=(
        "'evidenced' if the resume speaks to this at all; 'unstated' if the resume is simply "
        "silent about it; 'contradicted' if the resume actively indicates the candidate does "
        "NOT have it"))
    claim_ids: list[str] = Field(default_factory=list, description="ids of the claims that support this")
    rationale: str = Field(description="one sentence, naming the evidence")


class _Mapping(BaseModel):
    matches: list[_Match]


PROMPT = """Decide how well a candidate's claims evidence each role requirement.

STRENGTH SCALE
- strong:   direct evidence from a specific role or project
- moderate: closely related experience that plainly transfers
- weak:     tangential; some contact with the area but not the thing asked for
- missing:  no relevant evidence

TECHNOLOGY DISTINCTIONS - do not conflate these:
- Vector databases (ChromaDB, Qdrant, Milvus, Pinecone, Weaviate) are NOT graph databases.
- Graph databases (Neo4j, JanusGraph, ArangoDB) and knowledge-graph tools (SPARQL, RDF, OWL)
  are a different category. LangGraph is agent orchestration, NOT knowledge-graph technology.
- RAG is a TECHNIQUE. RAGAs and LangSmith are specific EVALUATION TOOLS. RAG pipeline
  experience does NOT evidence RAGAs or LangSmith.
- A cloud provider is not interchangeable with another. AWS experience is moderate evidence
  for a GCP requirement, never strong.

BASIS - judge this separately from strength, it matters more than strength for hard gates:
- 'unstated' means the document never addresses the requirement. Work authorisation, security
  clearance and visa status are almost never written on a resume: absent any mention, the
  correct answer is 'unstated', NEVER 'contradicted'.
- 'contradicted' requires positive evidence AGAINST - e.g. the requirement is a degree and the
  education section shows the candidate did not complete one.
- If in doubt between unstated and contradicted, choose 'unstated'.

HARD RULES
- Judge the BACKGROUND, never the writing. A blunt, duty-listing bullet from someone who has
  genuinely done the work is STRONG. A polished, metric-laden bullet describing adjacent work
  is MODERATE at best. If you find yourself rewarding phrasing, you have made an error.
- Use only what the claims state. Never infer experience that is not evidenced.
- Emit exactly one match per requirement, including the ones that are missing.

COMPUTED CAREER FACTS - these were calculated from the resume's own dates by the system, not
claimed by the candidate. Treat them as reliable. Requirements about years of experience,
seniority or leading a team are evidenced HERE, not in the skill list.
{career}

REQUIREMENTS:
{requirements}

CANDIDATE CLAIMS:
{claims}"""


def map_claims(
    claims: list[Claim],
    requirements: list[Requirement],
    employment: list[Employment] | None = None,
) -> list[Match]:
    if not requirements:
        return []
    req_block = "\n".join(f"[{r.id}] ({r.kind}) {r.text}" for r in requirements)
    # Shortlist before the expensive call. All 303 claims from a thorough extraction make a
    # ~33k-char prompt that times out and buries the ones that matter.
    claims = selector.select(claims, requirements)
    claim_block = "\n".join(
        f"[{c.id}] {c.skill[:110]}"
        + (f" - {c.years_claimed}y claimed" if c.years_claimed else "")
        + (f" - since {c.since_year}" if c.since_year else "")
        + (f" - level: {c.level}" if c.level else "")
        + f" | evidence: {c.evidence.text[:160]}"
        for c in claims
    ) or "(no claims extracted)"

    nonce = uuid.uuid4().hex[:8]
    result = llm.structured(
        "skill_map", _Mapping,
        PROMPT.format(
            career=derived.summarise(employment or []),
            requirements=req_block,
            claims=sanitize.wrap_untrusted(claim_block, nonce, "claims"),
        ),
    )

    by_id = {c.id: c for c in claims}
    seen: dict[str, Match] = {}
    for m in result.matches:
        if m.requirement_id not in {r.id for r in requirements}:
            continue
        strength = m.strength if m.strength in {"strong", "moderate", "weak", "missing"} else "missing"
        ids = [cid for cid in m.claim_ids if cid in by_id]
        basis = m.basis if m.basis in {"evidenced", "unstated", "contradicted"} else "unstated"
        seen[m.requirement_id] = Match(
            requirement_id=m.requirement_id,
            strength=strength,  # type: ignore[arg-type]
            basis=basis,  # type: ignore[arg-type]
            claim_ids=ids,
            rationale=m.rationale,
            evidence=[by_id[cid].evidence for cid in ids],
        )

    # A mapping that came back completely empty is not a candidate who matches nothing - it is
    # a call that did not do its job. Backfilling every requirement as "missing" turns that
    # into a confident 0%, which ranks a qualified person last and reads to a recruiter as
    # "unqualified" rather than "we failed to check". Seen live: a network engineer whose CV
    # listed Cisco routing, switching and firewalls scored 0% against a role asking for
    # exactly that, because the mapping call failed under a rate limit and nothing raised.
    if claims and not seen:
        raise RuntimeError(
            f"the mapping step returned no usable matches for any of {len(requirements)} "
            f"requirements, from {len(claims)} shortlisted claims - refusing to score this as "
            "0%. Re-run the CV."
        )

    # Any requirement the model skipped counts as missing. Dropping it instead would quietly
    # shrink the denominator and inflate everyone's coverage.
    for r in requirements:
        seen.setdefault(r.id, Match(requirement_id=r.id, strength="missing", basis="unstated",
                                    rationale="the resume does not address this"))
    return [seen[r.id] for r in requirements]
