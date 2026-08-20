"""The only place the app talks to a model.

Three jobs, in order of how much they matter for a live demo:

1. **Disk cache.** Every structured call is keyed by (model, schema, prompt) and stored as
   JSON. A pre-warmed cache makes the demo instant and survives the venue wifi dying.
2. **Offline mode.** ``FIT_HAPPENS_OFFLINE=1`` turns a cache miss into a loud error instead of
   a network call, so "does the demo still work unplugged?" is a question you can actually
   answer rather than hope about.
3. **Rate limiting.** The NIM free tier is ~40 requests/minute shared across models. Bulk
   corpus work would sail straight past that, so every call goes through one bucket.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from . import config

T = TypeVar("T", bound=BaseModel)

_RPM = 35  # a little under the documented ~40, because 429s cost more than the delay saves
_lock = threading.Lock()
_calls: list[float] = []
_clients: dict[str, ChatOpenAI] = {}


class OfflineCacheMiss(RuntimeError):
    """Raised when offline mode is on and the answer was never cached."""


def _throttle() -> None:
    with _lock:
        now = time.monotonic()
        cutoff = now - 60.0
        while _calls and _calls[0] < cutoff:
            _calls.pop(0)
        if len(_calls) >= _RPM:
            time.sleep(max(0.0, 60.0 - (now - _calls[0])) + 0.05)
        _calls.append(time.monotonic())


def _client(model: str) -> ChatOpenAI:
    if model not in _clients:
        _clients[model] = ChatOpenAI(
            model=model,
            base_url=config.base_url(),
            api_key=config.api_key(),
            temperature=config.models().get("temperature", 0.0),
            max_retries=config.models().get("max_retries", 3),
        )
    return _clients[model]


def _key(model: str, schema: type[BaseModel], prompt: str) -> str:
    payload = json.dumps(
        {"m": model, "s": schema.model_json_schema(), "p": prompt},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def structured(task: str, schema: type[T], prompt: str, *, model: str | None = None) -> T:
    """Run one schema-constrained call, cached on disk.

    The LLM's job stops at extracting and drafting. It never decides anything: scores,
    dates and verdicts are computed by the rules engine from what comes back here.
    """
    model = model or config.model_for(task)
    cache_file = config.CACHE_DIR / f"{_key(model, schema, prompt)}.json"

    if cache_file.exists():
        return schema.model_validate_json(cache_file.read_text())

    if config.offline():
        raise OfflineCacheMiss(
            f"offline mode: no cached answer for task={task!r} model={model!r}. "
            f"Run scripts/prewarm.py with the network up first."
        )

    _throttle()
    result = _client(model).with_structured_output(schema).invoke(prompt)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(result.model_dump_json(indent=2))
    return result


def cache_stats() -> dict[str, int]:
    files = list(config.CACHE_DIR.glob("*.json"))
    return {"entries": len(files), "bytes": sum(f.stat().st_size for f in files)}
