"""An application: a person applied, rather than a file being processed.

Uploaded CVs were named after the file, so an applicant appeared in the hiring dashboard as
`15118506`. That is a symptom of the deeper thing this fixes - the product had no notion of
someone applying at all, only of a recruiter feeding it documents.

Email is stored for one reason: so someone who loses their link can get it back. A link in an
email people delete is not a system of record.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..config import DATA_DIR

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


def looks_like_email(value: str) -> bool:
    return bool(EMAIL_RE.match((value or "").strip()))


def candidate_id_for(name: str, email: str) -> str:
    """Stable, readable, and unique enough. Readable because a recruiter reads it, and hashed
    because two people share a name far more often than a name-and-email."""
    base = re.sub(r"[^a-z0-9]+", "-", (name or "applicant").lower()).strip("-")[:32] or "applicant"
    tail = hashlib.sha256((email or name).lower().encode()).hexdigest()[:6]
    return f"{base}-{tail}"


class Application(BaseModel):
    candidate_id: str
    name: str
    email: str
    role_slug: str
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    cv_filename: str = ""


class ApplicationStore:
    def __init__(self, run: str = "demo"):
        self.dir = DATA_DIR / "runs" / run / "applications"

    def save(self, app: Application) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{app.candidate_id}.json").write_text(app.model_dump_json(indent=2))

    def get(self, candidate_id: str) -> Application | None:
        p = self.dir / f"{candidate_id}.json"
        return Application.model_validate_json(p.read_text()) if p.exists() else None

    def all(self) -> list[Application]:
        if not self.dir.exists():
            return []
        return [Application.model_validate_json(f.read_text()) for f in self.dir.glob("*.json")]


def find_by_email(email: str) -> list[tuple[str, Application]]:
    """Every application this address has made, across all roles."""
    from ..store import roles

    email = (email or "").strip().lower()
    if not email:
        return []
    out = []
    for r in roles():
        for a in ApplicationStore(r["slug"]).all():
            if a.email.lower() == email:
                out.append((r["slug"], a))
    return sorted(out, key=lambda x: x[1].at, reverse=True)
