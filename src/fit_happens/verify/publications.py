"""Publications and talks, via OpenAlex.

The challenge lists publications alongside GitHub as evidence CVs miss. OpenAlex is a free,
open catalogue of scholarly work with no key and no meaningful rate limit, which is the only
reason this is in scope: every alternative wanted a paid or scraped source, and a fake version
of this would be worse than admitting we do not have it.

Same three states and the same rule as everywhere else. Most people have never published
anything - that is the norm, not a deficiency - so `unsupported` here means almost nothing and
is worded to say so. Only ever runs when the candidate has granted the `publications` scope.
"""

from __future__ import annotations

import re

import httpx

from .. import config
from ..schemas import ExternalEvidence, Requirement, Span, Verification

API = "https://api.openalex.org/works"
# A polite mailto gets OpenAlex's faster pool. No key, no account.
MAILTO = "fit-happens-hackathon@example.org"

# Name lines look like a name and nothing else: two or three capitalised words, no digits, no
# job-title nouns. Cheap and deliberately conservative - a wrong name searches the wrong person.
NAME_LINE = re.compile(r"^\s*([A-Z][a-z'\-]{1,20}(?:\s+[A-Z][a-z'\-]{1,20}){1,2})\s*$")
TITLE_WORDS = re.compile(
    r"\b(manager|engineer|analyst|director|specialist|consultant|developer|administrator|"
    r"summary|experience|education|skills|profile|resume|curriculum|objective|highlights|"
    r"technician|coordinator|assistant|supervisor|architect|officer|lead)\b", re.I)
# Company names have the same shape as personal names. Searching the wrong author is worse
# than not searching: it attributes someone else's publications to this candidate.
# Resume section headings have the same shape as names too: "Core Qualifications", "Career
# Overview", "Professional Summary". Found by running against real CVs rather than fixtures.
SECTION_WORDS = re.compile(
    r"\b(core|career|professional|work|employment|key|areas|technical|additional|relevant|"
    r"qualifications|overview|history|expertise|proficienc\w*|accomplishments|achievements|"
    r"certifications|references|contact|personal|statement|interests|activities|affiliations|"
    r"competencies|strengths|background|training|awards|languages|publications)\b", re.I)
COMPANY_WORDS = re.compile(
    r"\b(corp|corporation|inc|llc|ltd|limited|gmbh|plc|company|holdings|group|solutions|"
    r"systems|services|technologies|consulting|partners|associates|university|college|"
    r"institute|hospital|bank|agency|department|ministry)\b", re.I)


def guess_author_name(text: str) -> str | None:
    """The candidate's name, if the document states it plainly. None rather than a guess."""
    for line in text.splitlines()[:12]:
        m = NAME_LINE.match(line)
        if (m and not TITLE_WORDS.search(line) and not COMPANY_WORDS.search(line)
                and not SECTION_WORDS.search(line)):
            return m.group(1)
    return None


def fetch_works(author: str, *, timeout: float = 15.0, limit: int = 25) -> list[dict]:
    cache = config.CACHE_DIR / f"oa_{re.sub(r'[^a-z0-9]', '_', author.lower())}.json"
    if cache.exists():
        import json

        return json.loads(cache.read_text())
    if config.offline():
        return []
    try:
        r = httpx.get(API, params={
            "filter": f"raw_author_name.search:{author}",
            "per-page": limit,
            "mailto": MAILTO,
        }, timeout=timeout)
        r.raise_for_status()
        works = [
            {
                "title": w.get("title") or "",
                "year": w.get("publication_year"),
                "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
                "citations": w.get("cited_by_count", 0),
                "url": w.get("doi") or w.get("id") or "",
                "concepts": [c.get("display_name", "") for c in (w.get("concepts") or [])[:6]],
            }
            for w in r.json().get("results", [])
        ]
    except Exception:
        works = []
    cache.parent.mkdir(parents=True, exist_ok=True)
    import json

    cache.write_text(json.dumps(works, indent=2))
    return works


def verify_publications(author: str, requirements: list[Requirement] | None = None,
                        max_items: int = 4) -> list[Verification]:
    works = fetch_works(author)
    if not works:
        return [Verification(
            claim_id="", skill="Published work", state="unsupported", source_scope="publications",
            note="No publications found under this name. Most people have never published "
                 "anything, so this is expected and is not a mark against the application.")]

    relevant = works
    if requirements:
        from ..fit.select import score_claim
        from ..schemas import Claim

        req_text = " ".join(r.text for r in requirements)

        def relevance(w: dict) -> float:
            probe = Claim(id="", skill=" ".join(w["concepts"][:4]) or w["title"][:80],
                          evidence=Span(text=w["title"][:200]))
            return max(score_claim(probe, r) for r in requirements) if requirements else 0.0

        relevant = sorted(works, key=lambda w: (-relevance(w), -(w["citations"] or 0)))

    out: list[Verification] = []
    for w in relevant[:max_items]:
        out.append(Verification(
            claim_id="", skill=w["title"][:90] or "Untitled work", state="undersold",
            source_scope="publications",
            evidence=[ExternalEvidence(
                name=w["title"][:90], detail=f"{w['venue']} {w['year'] or ''}".strip(),
                first_seen_year=w["year"], last_seen_year=w["year"],
                volume=w["citations"] or 0, url=w["url"])],
            note=f"published {w['year'] or 'undated'}"
                 + (f" in {w['venue']}" if w["venue"] else "")
                 + (f", cited {w['citations']} times" if w["citations"] else "")
                 + " - not mentioned on the CV"))
    if len(works) > max_items:
        out.append(Verification(
            claim_id="", skill=f"+{len(works) - max_items} further publications",
            state="undersold", source_scope="publications", note="also found under this name"))
    return out
