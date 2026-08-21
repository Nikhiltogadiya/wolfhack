"""What the candidate has allowed us to look at.

The sixth Responsible-AI bullet - *"User-controlled sharing: people decide which data is
visible"* - and the only one we previously failed. It is also the one with teeth, because it
has to actually gate the fetching rather than decorate it.

Three properties, each of which is a test:

1. **Nothing external is fetched before consent is granted.** Not fetched-then-hidden. The
   network call does not happen. Anything else is a promise we would be breaking silently.
2. **Withdrawing consent deletes what was gathered under it** and removes it from the
   recruiter's view. Consent you cannot withdraw is not consent.
3. **Every change is recorded with a time**, in the same audit trail the recruiter sees, so
   "the candidate declined GitHub" is visible rather than looking like an absence of evidence.

The CV itself is always in scope and cannot be switched off: they sent it to apply. Saying
otherwise would be theatre.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..config import DATA_DIR

# Each scope is one external source. Descriptions are shown verbatim to the candidate, so they
# say what we would actually do, in words a person can act on.
SCOPES: dict[str, dict[str, str]] = {
    "cv": {
        "label": "The CV you sent us",
        "detail": "Always included - this is the document you submitted with your application.",
        "locked": "true",
    },
    "github": {
        "label": "Your public GitHub",
        "detail": "We read public repository names, languages and dates. We never read private "
                  "repositories, and we do not read the contents of your code.",
        "locked": "",
    },
    "publications": {
        "label": "Published papers and talks",
        "detail": "We look up publications listed under your name in OpenAlex, a free and open "
                  "catalogue of scholarly work.",
        "locked": "",
    },
}

# REMOVED: a "community" scope covering open-source contributions and public technical writing.
# It was declared here and read by nothing, so a candidate could switch it on and no behaviour
# changed. A consent control that does nothing is worse than an absent one - it is precisely
# the claim this module exists to make, made falsely. Implementing it properly needs scraping
# personal sites and forums, which we are not doing, so it is gone rather than decorative.
DEFAULT_GRANTS = {k: (k == "cv") for k in SCOPES}


class ConsentEvent(BaseModel):
    at: str
    scope: str
    granted: bool
    actor: str = "candidate"


class Consent(BaseModel):
    token: str
    candidate_id: str
    grants: dict[str, bool] = Field(default_factory=lambda: dict(DEFAULT_GRANTS))
    history: list[ConsentEvent] = Field(default_factory=list)

    @field_validator("grants")
    @classmethod
    def _drop_retired_scopes(cls, grants: dict[str, bool]) -> dict[str, bool]:
        """SCOPES shrank once - the `community` scope was removed - and the records written
        before that still name it on disk. `summary()` does SCOPES[k]["label"] over these
        keys, so a retired scope set to true raises KeyError and 500s the candidate's own
        portal. Pruning here means nothing downstream has to know that happened; making each
        consumer defensive instead would just move the trap around.
        """
        return {k: v for k, v in grants.items() if k in SCOPES}

    def allows(self, scope: str) -> bool:
        if scope == "cv":
            return True
        return bool(self.grants.get(scope, False))

    def set(self, scope: str, granted: bool) -> bool:
        """Record a decision. Returns True if this REVOKED something previously granted,
        which is the caller's cue to delete what was gathered under it."""
        if scope not in SCOPES or SCOPES[scope]["locked"]:
            return False
        was = self.grants.get(scope, False)
        self.grants[scope] = granted
        self.history.append(ConsentEvent(
            at=datetime.now(UTC).isoformat(timespec="seconds"),
            scope=scope, granted=granted))
        return bool(was and not granted)

    def summary(self) -> str:
        on = [SCOPES[k]["label"] for k, v in self.grants.items() if v or k == "cv"]
        return ", ".join(on)


class ConsentStore:
    """One JSON file per candidate. The token is what the candidate holds; it is derived from
    the candidate id and a per-run secret so links cannot be guessed from an id."""

    def __init__(self, run: str = "demo"):
        self.dir = DATA_DIR / "runs" / run / "consent"
        self.dir.mkdir(parents=True, exist_ok=True)  # keyed by an existing role
        self._secret_file = self.dir / ".secret"
        if not self._secret_file.exists():
            self._secret_file.write_text(secrets.token_hex(16))
        self._secret = self._secret_file.read_text().strip()

    def token_for(self, candidate_id: str) -> str:
        return hashlib.sha256(f"{self._secret}:{candidate_id}".encode()).hexdigest()[:20]

    def _path(self, candidate_id: str) -> Path:
        return self.dir / f"{candidate_id}.json"

    def load(self, candidate_id: str) -> Consent:
        p = self._path(candidate_id)
        if p.exists():
            return Consent.model_validate_json(p.read_text())
        return Consent(token=self.token_for(candidate_id), candidate_id=candidate_id)

    def save(self, consent: Consent) -> None:
        self._path(consent.candidate_id).write_text(consent.model_dump_json(indent=2))

    def by_token(self, token: str) -> Consent | None:
        for f in self.dir.glob("*.json"):
            c = Consent.model_validate_json(f.read_text())
            if secrets.compare_digest(c.token, token):
                return c
        # not yet saved: derive from the ids we know about
        for f in (DATA_DIR / "runs" / "demo").glob("c_*.json"):
            cid = json.loads(f.read_text())["candidate_id"]
            if secrets.compare_digest(self.token_for(cid), token):
                return self.load(cid)
        return None
