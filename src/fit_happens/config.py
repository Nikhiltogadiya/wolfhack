"""Single source of truth for paths, model routing and tunable thresholds.

Nothing else in the codebase hard-codes a model id, a weight or a threshold. If you find one
inline, it belongs here.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
CORPUS_DIR = DATA_DIR / "corpus"

# ---- Fit Engine ----------------------------------------------------------------
# Fixed 70/30. Deliberately NOT derived from requirement counts: normalising by
# (n_required + 0.3 * n_preferred) makes the ratio drift with how many requirements a JD
# happens to list. The brief specifies a fixed split, so the split is fixed.
WEIGHT_REQUIRED = 0.70
WEIGHT_PREFERRED = 0.30

# Coverage credit per match strength. Applied identically to required and preferred, so
# prose quality has no path into either number.
STRENGTH_CREDIT = {"strong": 1.0, "moderate": 0.6, "weak": 0.2, "missing": 0.0}

# An unmet dealbreaker cannot be written around. It raises its own flag and caps the fit
# score, so such a candidate can never outrank a qualifying one. Capped rather than zeroed:
# the brief's own evidence table shows a worst candidate at 14%, not 0.
DEALBREAKER_CAP = 0.49

# ---- Slop Bouncer --------------------------------------------------------------
# Two independent flags, with distinct pattern ids AND distinct evidence spans, before
# anything may be called likely fabricated. House rule, enforced in corroborate.py.
MIN_INDEPENDENT_FLAGS = 2

# AI-text detection is only meaningful on a whole document. Liang et al. (Patterns 2023)
# measured a 61.22% false-positive rate for non-native English writers; Fraser et al. (JAIR)
# found detectors need >=100 words, ~200 for reliability. A resume bullet is 10-25 words, so
# per-bullet scoring is statistically meaningless and we refuse to do it.
MIN_WORDS_FOR_STYLE_SCORE = 100

# The grey band. Inside it we report "inconclusive" and say why, rather than pretending to a
# verdict the evidence cannot support.
STYLE_GREY_BAND = (0.35, 0.75)


@functools.lru_cache(maxsize=1)
def models() -> dict:
    return yaml.safe_load((CONFIG_DIR / "models.yaml").read_text())


def model_for(task: str) -> str:
    cfg = models()
    return cfg["tasks"].get(task, cfg["default"])


def base_url() -> str:
    return models()["provider"]["base_url"]


def api_key() -> str:
    env = models()["provider"]["api_key_env"]
    key = os.environ.get(env)
    if not key:
        raise RuntimeError(
            f"{env} is not set. Add it to ~/.bashrc. "
            f"Note: GET /v1/models is public, so a 200 there does not prove your key works."
        )
    return key


def thinking_disabled(task: str) -> bool:
    """Whether to switch the reasoning trace off for this task.

    On for judgement calls (skill mapping, the two LLM bluff patterns), off for mechanical
    extraction - where it measured 2.5-6x slower with no recall benefit.
    """
    return task in set(models().get("disable_thinking_for", []))


def offline() -> bool:
    """Replay-only mode. Any cache miss raises instead of hitting the network."""
    return os.environ.get("FIT_HAPPENS_OFFLINE", "").lower() in {"1", "true", "yes"}
