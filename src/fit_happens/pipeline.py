"""The nine-stage pipeline, wired as a LangGraph graph.

Stage order matters and follows the brief exactly. In particular **checkpoint 1 runs on the raw
resume before skill extraction**, which the intake doc changed from the whiteboard's ordering
on purpose: nothing downstream should ever be reading a document whose hidden content has not
already been found and excised.

    01 ingest            text out, hidden spans found and removed
    02 CP1 sloppiness    style read on the sanitised resume
    03 extract claims    chunked, parallel
    04 map to JD         external + internal requirements
    05 CP2 consistency   8 patterns, corroboration rule
    06 score             fixed 70/30, dealbreaker gate
    07 verify externally GitHub, when a handle exists
    08 questions         from gaps, corroborated flags, undersold evidence
    09 assemble          four separate scores, never blended
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .fit import extract_claims, map as mapper, questions as qgen, score as scorer
from .ingest import forensics
from .jd.model import JobDescription
from .schemas import CandidateResult, Requirement
from .slop import bluff, corroborate
from .slop.style import read_style
from .verify import credentials, freshness, github


class State(TypedDict, total=False):
    path: str
    jd: JobDescription
    requirements: list[Requirement]
    result: CandidateResult
    credentials: list
    document: object
    style: object
    claims: list
    employment: list
    matches: list
    fit: object
    flags: list
    cp2: object
    verifications: list
    questions: list


def n_ingest(s: State) -> State:
    return {"document": forensics.ingest(s["path"])}


def n_style(s: State) -> State:
    return {"style": read_style(s["document"].text)}


def n_extract(s: State) -> State:
    claims, employment = extract_claims.extract_claims(s["document"])
    return {"claims": claims, "employment": employment}


def n_map(s: State) -> State:
    return {"matches": mapper.map_claims(s["claims"], s["requirements"], s["employment"])}


def n_score(s: State) -> State:
    return {"fit": scorer.score_fit(s["matches"], s["requirements"])}


def n_cp2(s: State) -> State:
    flags = bluff.run_deterministic(
        s["document"].text, s["claims"], s["employment"], s["requirements"])
    # Hidden text is an authenticity signal in its own right, and a strong one: it is the only
    # pattern here where the candidate had to act deliberately to conceal something.
    for h in s["document"].hidden:
        flags.append(bluff._flag(
            "hidden_text", f"text hidden in the file: {h.provenance}", h.span,
            0.9 if h.looks_like_instruction else 0.6))
    return {"flags": flags, "cp2": corroborate.decide(flags, s["style"])}


def n_verify(s: State) -> State:
    """External evidence: public code, and credentials named as their issuers name them.

    The challenge names both - "CVs miss GitHub work, publications, certifications". Neither
    may lower a score: absence of public code or of a recognised credential is absence of
    information, not evidence against anyone.
    """
    creds = credentials.verify_credentials(s["document"].text, s["claims"])
    handles = github.find_handles(s["document"].text)
    if not handles:
        return {"verifications": [], "credentials": creds}
    profile = github.fetch_profile(handles[0])
    return {
        "verifications": github.verify_claims(s["claims"], profile, s["requirements"]),
        "credentials": creds,
    }


def n_questions(s: State) -> State:
    return {"questions": [
        q.model_dump() for q in qgen.generate(
            s["fit"], s["requirements"], s["cp2"].flags, s["verifications"])
    ]}


def build_graph():
    g = StateGraph(State)
    for name, fn in [
        ("ingest", n_ingest), ("cp1_style", n_style), ("extract", n_extract),
        ("map", n_map), ("cp2_claims", n_cp2), ("score", n_score),
        ("verify", n_verify), ("questions", n_questions),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "cp1_style")
    g.add_edge("cp1_style", "extract")
    g.add_edge("extract", "map")
    g.add_edge("map", "score")
    g.add_edge("score", "cp2_claims")
    g.add_edge("cp2_claims", "verify")
    g.add_edge("verify", "questions")
    g.add_edge("questions", END)
    return g.compile()


_GRAPH = None


def run_candidate(path: str | Path, jd: JobDescription, requirements: list[Requirement]) -> CandidateResult:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    out = _GRAPH.invoke({"path": str(path), "jd": jd, "requirements": requirements})

    fresh = freshness.assess(out["employment"])
    stem = Path(path).stem
    return CandidateResult(
        candidate_id=stem,
        name=stem,
        category=Path(path).parent.name,
        source_path=str(path),
        fit=out["fit"],
        style=out["style"],
        cp2=out["cp2"],
        document=out["document"],
        claims=out["claims"],
        employment=out["employment"],
        verifications=out.get("verifications", []),
        credentials=out.get("credentials", []),
        freshness_label=fresh.label,
        freshness_note=fresh.note,
        freshness_tone=fresh.tone,
        last_active_year=fresh.last_active_year,
        questions=out.get("questions", []),
        audit=[e.model_dump() for e in jd.audit],
    )
