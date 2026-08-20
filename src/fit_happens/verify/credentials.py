"""Verify the certifications a CV claims.

The challenge names this directly: *"Static evidence: CVs miss GitHub work, publications,
certifications, learning and communities."* GitHub is handled in github.py; this is the
credential half.

Three outcomes, and the naming matters as much as the logic:

* **recognised**  - the credential exists and is written the way its issuer writes it.
* **unrecognised** - we do not hold this one in our registry. That is a statement about our
  registry, not about the candidate. Certifications are numerous, regional and constantly
  added, so "we have not heard of it" must never read as "it is not real".
* **malformed**   - the name is a shape the issuing body does not use, e.g. a level that vendor
  does not offer. This is a specific, checkable inconsistency and the only one that becomes a
  flag - and even then only as one flag among the two that corroboration requires.

Deterministic, no model call: a credential is either written the way its issuer writes it or it
is not, and a candidate is entitled to an answer that does not change between runs.
"""

from __future__ import annotations

import re

from ..schemas import Claim, Span, Verification
from ..slop.knowledge import IMPOSSIBLE_CERT_PATTERNS, REAL_CERTIFICATIONS

# What actually claims to BE a credential. Deliberately excludes "training" and "course":
# including them turned "employee training", "training plan" and "training coordination" -
# which are duties - into rows saying we could not verify a certification the candidate never
# claimed to hold. A list of things we failed to check is worse than useless if most of the
# entries were never certifications.
CERT_CONTEXT = re.compile(r"(certifi\w*|credential|licen[sc]ed?|accredit\w*|chartered)\b", re.I)
# ...unless the phrase is plainly describing work rather than a qualification.
NOT_A_CREDENTIAL = re.compile(
    r"\b(training|coordination|plan|program|delivery|management|support|employees?|staff|"
    r"users?|materials?|documentation|sessions?)\b", re.I)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9+ ]", " ", text.lower()).strip()


def find_certifications(text: str) -> list[tuple[str, str]]:
    """Return (canonical_name, matched_text) for every credential we recognise in the document.

    Longest key first, so "comptia security+" is not resolved as the shorter "security+" and
    reported under a less specific name than the candidate actually wrote.
    """
    flat = " " + re.sub(r"\s+", " ", _normalise(text)) + " "
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key in sorted(REAL_CERTIFICATIONS, key=len, reverse=True):
        pattern = re.escape(_normalise(key)).replace(r"\+", r"\+")
        if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", flat):
            canonical = REAL_CERTIFICATIONS[key]
            if canonical not in seen:
                seen.add(canonical)
                found.append((canonical, key))
    return found


def verify_credentials(
    text: str,
    claims: list[Claim] | None = None,
    max_unverifiable: int = 4,
) -> list[Verification]:
    out: list[Verification] = []
    # Track BOTH the canonical name and the form the candidate actually wrote. Matching only
    # on the canonical name reported "A+ Certified" as unverifiable while simultaneously
    # reporting "CompTIA A+" as verified - the same credential, listed twice, contradicting
    # itself in the same panel.
    recognised: set[str] = set()

    for canonical, matched in find_certifications(text):
        recognised.add(_normalise(canonical))
        recognised.add(_normalise(matched))
        out.append(Verification(
            claim_id="", skill=canonical, state="corroborated",
            note=f"named as its issuer names it ({matched})"))

    for pattern, why in IMPOSSIBLE_CERT_PATTERNS:
        if m := pattern.search(text):
            out.append(Verification(
                claim_id="", skill=m.group(0), state="unsupported",
                note=f"not how that credential is issued - {why}"))

    # Claims that look like credentials but are not in the registry. Reported so a recruiter
    # can see what we could NOT check, rather than us quietly checking nothing.
    if claims:
        unchecked: list[Verification] = []
        seen: set[str] = set()
        for c in claims:
            label = c.skill.strip()
            norm = _normalise(label)
            if not CERT_CONTEXT.search(label) or NOT_A_CREDENTIAL.search(label):
                continue
            if any(norm in k or k in norm for k in recognised if len(k) > 3):
                continue
            # collapse "Microsoft Certified", "Microsoft Certified Professional -" etc.
            if any(norm in k or k in norm for k in seen if len(k) > 6):
                continue
            seen.add(norm)
            unchecked.append(Verification(
                claim_id=c.id, skill=label, state="unsupported",
                note="not in our credential registry - we could not check this one, which says "
                     "nothing about whether it is genuine"))
        out.extend(unchecked[:max_unverifiable])
        if len(unchecked) > max_unverifiable:
            out.append(Verification(
                claim_id="", skill=f"+{len(unchecked) - max_unverifiable} further credentials",
                state="unsupported",
                note="also outside our registry. Reported as a count rather than a list, "
                     "because a long roster of things we could not check reads as doubt we "
                     "have not earned"))
    return out


def unverifiable_count(verifications: list[Verification]) -> int:
    return sum(1 for v in verifications if v.state == "unsupported")
