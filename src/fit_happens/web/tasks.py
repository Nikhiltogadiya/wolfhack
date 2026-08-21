"""Background processing for uploads, and somewhere to read its progress from.

A CV takes 30-60 seconds cold: several LLM round trips for chunked extraction, then mapping.
Doing that inside the request means a browser spinner for a minute with no idea whether
anything is happening, and a timeout if the provider is slow. So uploads return immediately and
the page reports progress.

State lives in a JSON file per role rather than in memory, for two reasons: uvicorn's reloader
restarts the process on any edit and would silently lose in-flight state, and a file can be
inspected while debugging a demo that is misbehaving.
"""

from __future__ import annotations

import json
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_DIR

_lock = threading.Lock()


def _path(slug: str) -> Path:
    d = DATA_DIR / "runs" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d / "tasks.json"


def _read(slug: str) -> dict:
    p = _path(slug)
    if not p.exists():
        return {"items": []}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"items": []}


def _write(slug: str, data: dict) -> None:
    _path(slug).write_text(json.dumps(data, indent=1))


def start(slug: str, name: str) -> str:
    """Register a file as queued. Returns its id."""
    with _lock:
        d = _read(slug)
        tid = f"{name}-{len(d['items'])}"
        d["items"].append({
            "id": tid, "name": name, "state": "queued", "detail": "waiting to start",
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": ""})
        _write(slug, d)
    return tid


def update(slug: str, tid: str, state: str, detail: str = "", error: str = "") -> None:
    with _lock:
        d = _read(slug)
        for it in d["items"]:
            if it["id"] == tid:
                it.update(state=state, detail=detail, error=error,
                          at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        _write(slug, d)


# A task that has claimed to be running for longer than this is not running. The most common
# cause is uvicorn's --reload restarting the process mid-task: the state file survives, the
# thread does not, and the page spins forever on work that will never finish. Measured: a long
# CV takes ~150s cold, so the cutoff has to be comfortably above that.
STALE_AFTER_SECONDS = 480


def _age(item: dict) -> float:
    from datetime import datetime, timezone

    try:
        started = datetime.fromisoformat(item["at"])
        return (datetime.now(timezone.utc) - started).total_seconds()
    except Exception:
        return 0.0


def _reap_stale(slug: str) -> None:
    with _lock:
        d = _read(slug)
        changed = False
        for it in d["items"]:
            if it["state"] in {"queued", "running"} and _age(it) > STALE_AFTER_SECONDS:
                it.update(state="failed", detail="",
                          error="processing stopped before it finished - most likely the server "
                                "restarted. Upload the file again.")
                changed = True
        if changed:
            _write(slug, d)


def pending(slug: str) -> list[dict]:
    _reap_stale(slug)
    return [i for i in _read(slug)["items"] if i["state"] in {"queued", "running"}]


def recent(slug: str, limit: int = 8) -> list[dict]:
    return list(reversed(_read(slug)["items"]))[:limit]


def failed(slug: str) -> list[dict]:
    return [i for i in _read(slug)["items"] if i["state"] == "failed"]


def clear_finished(slug: str) -> None:
    with _lock:
        d = _read(slug)
        d["items"] = [i for i in d["items"] if i["state"] in {"queued", "running"}]
        _write(slug, d)


def process_cv(slug: str, path: str, tid: str) -> None:
    """Run one CV through the pipeline. Never raises: a failed upload must show as a failed
    upload, not take the server down or vanish without trace."""
    from ..candidate.consent import ConsentStore
    from ..jd.model import JobDescription
    from ..pipeline import run_candidate
    from ..schemas import Requirement
    from ..store import Run

    try:
        update(slug, tid, "running", "reading the document")
        run = Run(slug)
        role = run.load_role()
        if not role:
            update(slug, tid, "failed", "", "this role has no job description yet")
            return
        jd = JobDescription.model_validate(role["jd"])
        reqs = [Requirement(**r) for r in role["requirements"]]
        cid = Path(path).stem
        consent = ConsentStore(slug).load(cid)

        update(slug, tid, "running", "extracting claims and matching to the role")
        # An application carries the name the person typed. Without this the recruiter sees a
        # filename, which is how one applicant came to be listed as "15118506".
        from ..candidate.applications import ApplicationStore

        appn = ApplicationStore(slug).get(cid)
        result = run_candidate(path, jd, reqs, consent, display_name=appn.name if appn else "")
        run.save_candidate(result)
        ConsentStore(slug).save(consent)
        update(slug, tid, "done", f"{result.fit.score:.0%} fit · {len(result.claims)} claims")
    except Exception as exc:
        update(slug, tid, "failed", "", f"{type(exc).__name__}: {exc}"[:200])
        traceback.print_exc()
