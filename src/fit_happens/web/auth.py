"""A gate on the hiring area.

Found by opening the site as a candidate: every recruiter page answered 200 with no
credentials, so an applicant could read another applicant's evidence, their flags, and the
questions being asked of them. That is a privacy failure, not a missing feature.

**This is not production authentication and does not pretend to be.** A real deployment needs
per-user accounts, SSO, and a record of who viewed which application - the last one especially,
because "who looked at this candidate's file" is exactly the kind of question a GDPR subject
access request asks. This is a shared team passcode in a signed cookie. It stops a candidate
walking into the hiring dashboard, which is the actual defect found.

If no passcode is configured the area stays open and says so on every page, because a lock that
is silently unlocked is worse than a visible absence of one.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import Request
from fastapi.responses import RedirectResponse

COOKIE = "fh_team"
ENV_VAR = "FIT_HAPPENS_TEAM_PASSCODE"


def configured() -> bool:
    return bool(os.environ.get(ENV_VAR, "").strip())


def _expected() -> str:
    secret = os.environ.get(ENV_VAR, "").strip()
    return hashlib.sha256(f"fit-happens:{secret}".encode()).hexdigest()[:32]


def check(passcode: str) -> bool:
    if not configured():
        return True
    return hmac.compare_digest(passcode.strip(), os.environ.get(ENV_VAR, "").strip())


def is_signed_in(request: Request) -> bool:
    if not configured():
        return True
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), _expected())


def sign_in(response) -> None:
    response.set_cookie(COOKIE, _expected(), httponly=True, samesite="lax", max_age=60 * 60 * 12)


def sign_out(response) -> None:
    response.delete_cookie(COOKIE)


def require(request: Request):
    """Returns a redirect if the caller is not signed in, otherwise None."""
    if is_signed_in(request):
        return None
    return RedirectResponse(f"/hiring/sign-in?next={request.url.path}", status_code=303)
