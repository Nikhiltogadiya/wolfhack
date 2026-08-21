"""External JD text -> typed requirements.

Two passes on purpose. The LLM splits prose into atomic requirements and labels each one; a
deterministic pass then overrides the required/preferred call using explicit cue words, because
that distinction drives 70% of the score and a model that drifts on it drifts the whole ranking.
Cue lists adapted from ai-CV-cover-letter's requirement_classifier.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .. import llm
from ..schemas import Requirement

PREFERRED_CUES = re.compile(
    r"\b(nice[- ]to[- ]have|preferred|preferably|desirable|desired|a plus|bonus|advantageous|"
    r"ideally|would be great|wünschenswert|von vorteil|idealerweise)\b", re.IGNORECASE)
REQUIRED_CUES = re.compile(
    r"\b(must[- ]have|must |required|requirement|essential|mandatory|minimum|at least|"
    r"you (will )?need|non[- ]negotiable|vorausgesetzt|zwingend|erforderlich)\b", re.IGNORECASE)
# Hard gates: things no amount of good prose substitutes for. Written as separate alternatives
# rather than one clause because job adverts phrase work authorisation half a dozen ways and an
# earlier version caught "right to work" and "work authorisation" but missed "eligible to work"
# and "legally authorised to work" - which is most of them.
DEALBREAKER_CUES = re.compile(
    r"\b(degree|bachelor|master|phd|diploma|licen[sc]ed?|certifi\w*|clearance|"
    r"registered|accredited|chartered)\b"
    r"|\b(work\s+(authoris|authoriz|permit|eligib|status)\w*"
    r"|(eligib|authoris|authoriz|entitle|permitt|licen[sc]e)\w*\s+to\s+work"
    r"|right\s+to\s+work|visa|work\s+permit|sponsorship"
    r"|legally\s+(able|entitled|authoris\w+|authoriz\w+|permitted))\b"
    # "must hold" is a hard-gate phrasing whatever follows it, which saves listing every
    # credential acronym an advert might name. "Must hold a CISSP" was missed because bare
    # acronyms are not in the credential pattern and listing them all is a losing game.
    r"|\b(must|need\s+to|required\s+to)\s+(hold|possess|maintain|obtain|be\s+licen[sc]ed)\b",
    re.IGNORECASE)


class _ParsedReq(BaseModel):
    text: str = Field(description="one atomic requirement, in the JD's own words where possible")
    kind: str = Field(description="'required' or 'preferred'")
    category: str = Field(description="skill | experience | credential | eligibility | domain")


class _ParsedJD(BaseModel):
    title: str
    requirements: list[_ParsedReq]


PROMPT = """You are parsing a job advert into atomic requirements for a hiring system.

Rules:
- One requirement per item. Split compound sentences: "Python and Kubernetes" is TWO items.
- Use the advert's own wording where you can. Do not invent requirements it does not state.
- category: 'skill' (a tool or technology), 'experience' (years or a kind of work),
  'credential' (degree, certification, licence), 'eligibility' (work authorisation, clearance),
  'domain' (an industry or problem area).
- kind: 'required' if the advert presents it as necessary, 'preferred' if it is a nice-to-have.

{jd}"""


def parse_jd(external_text: str, title: str = "") -> tuple[str, list[Requirement]]:
    parsed = llm.structured("jd_parse", _ParsedJD, PROMPT.format(jd=external_text))

    out: list[Requirement] = []
    for i, r in enumerate(parsed.requirements):
        kind = r.kind if r.kind in {"required", "preferred"} else "required"
        # Deterministic override: explicit cue words beat the model's judgement, in both
        # directions. A "nice to have" the model marked required would silently inflate the
        # 70% bucket for every candidate scored against this role.
        if PREFERRED_CUES.search(r.text):
            kind = "preferred"
        elif REQUIRED_CUES.search(r.text):
            kind = "required"
        category = r.category if r.category in {"skill", "experience", "credential", "eligibility", "domain"} else "skill"
        out.append(
            Requirement(
                id=f"ext-{i}",
                text=r.text.strip(),
                kind=kind,  # type: ignore[arg-type]
                category=category,  # type: ignore[arg-type]
                # A dealbreaker is a hard gate: no amount of good prose substitutes for a
                # licence you do not hold. Only ever set deterministically.
                dealbreaker=bool(kind == "required" and DEALBREAKER_CUES.search(r.text)),
                source="external",
            )
        )
    return (parsed.title or title), out
