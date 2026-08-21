"""Check resume claims against public GitHub activity.

This is the piece that answers the challenge's own words - *"CVs miss GitHub work,
publications, certifications"* - and it turns Slop Bouncer from *is this internally
consistent?* into *does this match observable reality?*

Three outcomes per claim, and the third is the interesting one:

* **corroborated** - the claim and the commit history agree.
* **unsupported** - this source had nothing to say. **Not an accusation.** Most work is not
  public.
* **undersold** - real, dated evidence of a skill the resume never mentions.

`undersold` is the case worth leading a demo with: the same machinery pointed the other way,
finding something *for* the candidate rather than against them. It is also the honest answer to
why a verification feature is not just surveillance.

THE HARD RULE, enforced in `verify_claims` and pinned by
`test_missing_github_never_lowers_any_score`: **absence of a GitHub profile is never a negative
signal.** Most people have none - closed-source employers, NDAs, caring responsibilities, early
career, or simply not being a software engineer. Penalising that would be a fairness failure
aimed squarely at the challenge's own bias-monitoring requirement.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime

import httpx

from .. import config
from ..fit.select import score_claim
from ..schemas import Claim, ExternalEvidence, ExternalProfile, Requirement, Span, Verification

# GitHub topics that describe a project rather than a capability. Without this filter a single
# active profile yields fifty "undersold" rows - json, http, server, backend, web - which buries
# the two that actually mean something and makes the feature worse than not having it.
GENERIC_TOPICS = {
    "web", "webapp", "website", "http", "https", "json", "api", "apis", "server", "backend",
    "frontend", "fullstack", "app", "application", "library", "framework", "tool", "tools",
    "cli", "utility", "utils", "boilerplate", "template", "starter", "example", "examples",
    "demo", "sample", "tutorial", "learning", "course", "practice", "test", "testing",
    "automation", "generator", "config", "configuration", "setup", "development", "dev",
    "production", "open-source", "opensource", "hacktoberfest", "awesome", "list", "docs",
    "documentation", "portfolio", "personal", "project", "projects", "code", "software",
    "pull-requests", "github-app", "github-actions", "async", "oidc", "jwt", "swagger",
}

API = "https://api.github.com"
_H = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"

# Two shapes, because CVs use both and only the first was handled. A CV that says
# "GitHub: janedoe" - one of the most common ways anyone writes it - produced no handle at
# all, so the candidate was treated exactly like one with no public code. Hard rule 5 says
# absence of GitHub must never cost a candidate; a regex that manufactures that absence
# turns the rule into a lie for everyone who did not paste a full URL.
HANDLE_RES = [
    re.compile(rf"github\.com/({_H})\b", re.I),
    # "GitHub: janedoe", "Github - janedoe", "GitHub profile: @janedoe".
    # An explicit separator is required: matching bare "GitHub janedoe" would swallow the
    # next word of any sentence that merely mentions GitHub.
    re.compile(rf"\bgithub(?:\s+(?:profile|handle|username|user|id|account))?\s*[:\-\u2013\u2014]\s*@?({_H})\b", re.I),
]

# Paths that look like handles but are not people, plus the words most likely to follow a
# "GitHub:" label in prose rather than a handle.
NOT_HANDLES = {"about", "features", "pricing", "topics", "collections", "trending", "events",
               "sponsors", "readme", "explore", "marketplace", "orgs", "enterprise", "apps",
               "com", "www", "http", "https", "and", "or", "for", "the", "my", "me", "i",
               "see", "is", "was", "available", "on", "at", "in", "profile", "profiles",
               "link", "links", "username", "handle", "account", "repo", "repos",
               "repositories", "portfolio", "yes", "no", "n", "a", "used", "using", "via"}


def find_handles(text: str) -> list[str]:
    seen: list[str] = []
    for pattern in HANDLE_RES:
        for m in pattern.finditer(text or ""):
            h = m.group(1)
            if h.lower() not in NOT_HANDLES and h.lower() not in {s.lower() for s in seen}:
                seen.append(h)
    return seen


def _cache_path(handle: str) -> "os.PathLike":
    key = hashlib.sha256(f"github:{handle.lower()}".encode()).hexdigest()[:24]
    return config.CACHE_DIR / f"gh_{key}.json"


def forget(cv_text: str) -> int:
    """Delete the cached lookups this CV's handles produced, and only those.

    Withdrawal used to glob every `gh_*.json` in the cache, so one candidate revoking GitHub
    deleted the cached lookups of every candidate in every role. The cache is keyed by handle,
    and the handles come from the CV, so the candidate's own entries are recoverable exactly.
    """
    n = 0
    for handle in find_handles(cv_text):
        path = _cache_path(handle)
        if path.exists():
            path.unlink(missing_ok=True)
            n += 1
    return n


def fetch_profile(handle: str, *, timeout: float = 20.0) -> ExternalProfile:
    """Public repo metadata for one handle, cached to disk like every other network call.

    Unauthenticated GitHub allows 60 requests/hour, which one demo would exhaust; with
    GITHUB_TOKEN it is 5,000. Either way the cache means a rehearsed demo makes no calls.
    """
    cache = _cache_path(handle)
    if cache.exists():
        return ExternalProfile.model_validate_json(cache.read_text())

    if config.offline():
        return ExternalProfile(handle=handle, found=False, error="offline: no cached profile")

    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    profile = ExternalProfile(handle=handle)
    try:
        with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
            user = client.get(f"{API}/users/{handle}")
            if user.status_code == 404:
                profile.error = "no such user"
                cache.write_text(profile.model_dump_json(indent=2))
                return profile
            user.raise_for_status()
            profile.found = True
            profile.public_repos = user.json().get("public_repos", 0)

            repos = client.get(f"{API}/users/{handle}/repos",
                               params={"per_page": 100, "sort": "pushed", "type": "owner"})
            repos.raise_for_status()
            by_language: dict[str, dict] = {}
            for r in repos.json():
                if r.get("fork"):
                    continue  # a fork is not evidence of having written anything
                lang = r.get("language")
                created = _year(r.get("created_at"))
                pushed = _year(r.get("pushed_at"))
                for name in filter(None, [lang, *r.get("topics", [])]):
                    e = by_language.setdefault(name.lower(), {
                        "name": name, "first": created, "last": pushed, "n": 0, "url": ""})
                    e["n"] += 1
                    if created and (not e["first"] or created < e["first"]):
                        e["first"] = created
                    if pushed and (not e["last"] or pushed > e["last"]):
                        e["last"] = pushed
                    if not e["url"]:
                        e["url"] = r.get("html_url", "")
            profile.evidence = [
                ExternalEvidence(name=v["name"], first_seen_year=v["first"], last_seen_year=v["last"],
                                 volume=v["n"], url=v["url"],
                                 detail=f"{v['n']} public repo(s), {v['first']}-{v['last']}")
                for v in sorted(by_language.values(), key=lambda x: -x["n"])
            ]
    except Exception as exc:  # network failure must degrade to "no evidence", never to a penalty
        profile.error = f"{type(exc).__name__}: {exc}"

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(profile.model_dump_json(indent=2))
    return profile


def _year(iso: str | None) -> int | None:
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00")).year
    except Exception:
        return None


def _matches(skill: str, evidence_name: str) -> bool:
    a = re.sub(r"[^a-z0-9+#]", "", skill.lower())
    b = re.sub(r"[^a-z0-9+#]", "", evidence_name.lower())
    return bool(a) and bool(b) and (a == b or (len(a) > 3 and len(b) > 3 and (a in b or b in a)))


def verify_claims(
    claims: list[Claim],
    profile: ExternalProfile,
    requirements: list[Requirement] | None = None,
    max_undersold: int = 5,
) -> list[Verification]:
    """Resolve each claim against the profile, and surface what the resume left out.

    Returns an EMPTY list when there is no usable profile. That is deliberate: no profile means
    no information, and no information must produce no verifications rather than a page of
    `unsupported` rows that read as suspicion.
    """
    if not profile.usable:
        return []

    out: list[Verification] = []
    matched_evidence: set[str] = set()

    for c in claims:
        hits = [e for e in profile.evidence if _matches(c.skill, e.name)]
        if hits:
            matched_evidence.update(e.name.lower() for e in hits)
            span = f"{min(h.first_seen_year or 9999 for h in hits)}-{max(h.last_seen_year or 0 for h in hits)}"
            out.append(Verification(
                claim_id=c.id, skill=c.skill, state="corroborated", evidence=hits,
            source_scope="github",
                note=f"public repositories using {c.skill} span {span}"))
        else:
            out.append(Verification(
                claim_id=c.id, skill=c.skill, state="unsupported", evidence=[],
                source_scope="github",
                note="no public repository evidence - most work is not public, so this is not "
                     "a mark against the claim"))

    # The other direction: real, dated evidence the resume never claims. Ranked by relevance
    # to THIS role and capped, because "you also have 50 GitHub topics" is noise; "you have
    # two years of Docker and this role asks for it" is the finding.
    claimed = {re.sub(r"[^a-z0-9+#]", "", c.skill.lower()) for c in claims}
    candidates: list[ExternalEvidence] = []
    for e in profile.evidence:
        if e.name.lower() in matched_evidence or e.volume < 2:
            continue
        if e.name.lower() in GENERIC_TOPICS:
            continue
        key = re.sub(r"[^a-z0-9+#]", "", e.name.lower())
        if key and not any(key in c or c in key for c in claimed if len(c) > 3):
            candidates.append(e)

    if requirements:
        def relevance(ev: ExternalEvidence) -> float:
            probe = Claim(id="", skill=ev.name, evidence=Span(text=ev.name))
            return max(score_claim(probe, r) for r in requirements)

        candidates = [e for e in candidates if relevance(e) >= 55]
        candidates.sort(key=lambda e: (-relevance(e), -e.volume))
    else:
        candidates.sort(key=lambda e: -e.volume)

    # Collapse variants of the same thing: docker / docker-image / dockerfile / docker-compose
    # are one finding, and listing four of them reads as padding. Keep the highest-volume form.
    collapsed: list[ExternalEvidence] = []
    for e in candidates:
        stem = re.sub(r"[^a-z0-9]", "", e.name.lower())
        if any(stem.startswith(re.sub(r"[^a-z0-9]", "", k.name.lower())[:6])
               or re.sub(r"[^a-z0-9]", "", k.name.lower()).startswith(stem[:6])
               for k in collapsed):
            continue
        collapsed.append(e)
    candidates = collapsed

    for e in candidates[:max_undersold]:
        relevant = " - and this role asks for it" if requirements else ""
        out.append(Verification(
            claim_id="", skill=e.name, state="undersold", evidence=[e],
            source_scope="github",
            note=f"{e.detail} using {e.name}, not mentioned anywhere on the resume{relevant}"))
    return out
