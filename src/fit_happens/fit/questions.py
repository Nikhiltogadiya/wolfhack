"""Turn gaps and corroborated flags into questions a recruiter can actually send.

Two rules shape everything here:

1. **A deterministic template always exists.** The model only ever rewrites a question that is
   already complete and correct. If it is unavailable, slow, or refuses, the recruiter still
   gets a usable question. A demo that blanks because an API call failed is not a demo.

2. **Questions are asked, not alleged.** Every one is phrased as a request for information,
   never as an accusation - including the ones generated from an authenticity flag. The brief
   is explicit that flagging is not a finding of dishonesty, and the wording is where that
   promise is either kept or quietly broken.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .. import llm
from ..schemas import FitScore, Flag, Requirement, Verification

MAX_QUESTIONS = 6


class FollowUp(BaseModel):
    question: str
    reason: str
    source: str          # "gap" | "flag" | "confirmation" | "undersold"
    requirement_id: str = ""
    severity: str = "minor"


class _Polished(BaseModel):
    questions: list[str] = Field(description="the rewritten questions, same order, same meaning")


_LEADING_MODAL = re.compile(
    r"^\s*(you\s+)?(must|should|need\s+to|will\s+need\s+to|are\s+required\s+to)\s+(have|be|hold|possess)?\s*",
    re.IGNORECASE)


def _clean(requirement_text: str) -> str:
    """Strip the modal a JD writes requirements with.

    Job adverts phrase requirements as commands - "Must have the right to work in Germany" -
    and dropping that straight into a sentence produces "The role requires Must have the right
    to work in Germany". The template has to read correctly on its own, because the model
    polish that would smooth it over is the part we cannot depend on.
    """
    return _LEADING_MODAL.sub("", requirement_text).rstrip(".").strip() or requirement_text


def _template(gap_text: str, severity: str) -> str:
    gap_text = _clean(gap_text)
    if severity == "critical":
        # A colon rather than a clause. Requirement text is an arbitrary fragment lifted from
        # someone else's advert - "the right to work in Germany", "legally entitled to work in
        # the EU", "Bachelor's degree or equivalent" - and no single sentence frame reads
        # correctly around all of them. A colon does.
        return (f"One requirement for this role is not addressed in your CV: {gap_text}. "
                f"Could you tell us where you stand on this?")
    # Deliberately NOT lowercased: it turns "Active Directory" into "active directory", which
    # reads as careless in a message an employer sends to a candidate.
    return (f"We could not find evidence of this in your CV: {gap_text}. Is that something "
            f"you have worked on?")


def _flag_template(flag: Flag) -> str:
    quote = flag.span.text.strip()[:120]
    if flag.pattern_id == "expertise_predates_technology":
        return f"Your CV says \"{quote}\". Could you walk us through the timeline on that?"
    if flag.pattern_id == "overlapping_employment":
        return (f"Two roles on your CV overlap in time ({quote}). Were these concurrent, and if "
                f"so how were they arranged?")
    if flag.pattern_id == "jd_echo":
        return ("Several phrases in your CV closely match the wording of our advert. Could you "
                "describe this experience in your own words?")
    if flag.pattern_id == "duplicate_bullet":
        return f"The same description appears under two roles (\"{quote}\"). What differed between them?"
    return f"Could you give us more detail on this: \"{quote}\"?"


def generate(
    fit: FitScore,
    requirements: list[Requirement],
    flags: list[Flag] | None = None,
    verifications: list[Verification] | None = None,
    *,
    polish: bool = True,
) -> list[FollowUp]:
    by_id = {r.id: r for r in requirements}
    out: list[FollowUp] = []

    order = {"critical": 0, "major": 1, "minor": 2}
    for gap in sorted(fit.gaps, key=lambda g: order.get(g.severity, 9)):
        req = by_id.get(gap.requirement_id)
        if not req:
            continue
        out.append(FollowUp(
            question=_template(gap.text, gap.severity),
            reason=("this is a hard requirement your CV does not address"
                    if gap.needs_confirmation else f"{gap.severity} gap against a {req.kind} requirement"),
            source="confirmation" if gap.needs_confirmation else "gap",
            requirement_id=gap.requirement_id, severity=gap.severity,
        ))

    for f in (flags or []):
        out.append(FollowUp(question=_flag_template(f), reason=f.description,
                            source="flag", severity="major"))

    # The friendly one. Worth asking even when nothing is wrong, and it is the question that
    # shows the tool is not purely adversarial.
    for v in (verifications or []):
        if v.state == "undersold":
            out.append(FollowUp(
                question=(f"We noticed public work using {v.skill} that your CV does not mention. "
                          f"Would you like to tell us about it?"),
                reason=v.note, source="undersold", severity="minor"))

    out = out[:MAX_QUESTIONS]
    if polish and out:
        try:
            prompt = (
                "Rewrite each question so it sounds like a person wrote it. Keep the meaning and "
                "the order exactly. Keep each to one or two sentences.\n"
                "Rules: ask for information, never allege anything. Do not say 'discrepancy', "
                "'inconsistency', 'flagged' or 'concern'. Do not add questions. Do not merge "
                "them. Return exactly the same number you were given.\n\n"
                + "\n".join(f"{i + 1}. {q.question}" for i, q in enumerate(out))
            )
            polished = llm.structured("question_gen", _Polished, prompt)
            if len(polished.questions) == len(out):
                for q, better in zip(out, polished.questions):
                    # The prompt numbers the questions so order is unambiguous, and the model
                    # helpfully numbers them back. Strip it, or every question a recruiter
                    # sends starts with "3.".
                    better = re.sub(r"^\s*\d+[.)]\s*", "", better).strip()
                    if better:
                        q.question = better
        except Exception:
            pass  # the templates are already correct; polish is a nicety, never a dependency
    return out
