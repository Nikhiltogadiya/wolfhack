"""Checkpoint 1 - the vibe check.

Deliberately NOT a neural AI-text classifier. Liang et al. (Patterns 2023) measured a **61.22%
average false-positive rate** across seven detectors on TOEFL essays by non-native English
writers, against near-perfect accuracy on native-speaker essays; prompting the same essays for
richer vocabulary dropped it to 11.45%. The mechanism is low perplexity, so every
perplexity-based detector inherits the bias, and resumes are terse, formulaic and frequently
written by non-native speakers - the worst possible case.

So this scores named, interpretable patterns instead, each of which points at a specific span
a human can read and disagree with. Those are not perplexity, so they do not inherit the bias,
and a candidate can be told exactly what fired.

Three hard rules, enforced below:
  * scored on the WHOLE document, never per bullet - a bullet is 10-25 words, far too short for
    any of this to mean anything;
  * a wide grey band, reported as inconclusive rather than resolved into a verdict;
  * the output can never, on its own, produce anything stronger than `inconclusive`.

WHAT WE MEASURED, and why the third rule is not just caution.
We calibrated on 60 real resumes and LLM rewrites of the SAME resumes (`scripts/calibrate.py`,
`scripts/feature_analysis.py`). Share of rewrites exceeding the human 90th percentile:

    em dashes            27%      <- the only signal with real separation
    stock phrases/100w   18%
    rule of three         8%
    stock phrase types    3%
    self-significance     2%
    "not just X but Y"    0%
    copula avoidance      0%

The brief's four headline "vibe check" patterns are at or near zero. A detector built on them
scores 0% detection at 0% false positives on real data - it fires only on caricature. We are
reporting that rather than lowering thresholds until the number looks better, because the
threshold that would buy 27% detection costs flagging one real person in ten.
"""

from __future__ import annotations

import re
import statistics

from .. import config
from ..schemas import Flag, Span, StyleRead

STOCK_PHRASES = [
    "leveraged", "leveraging", "spearheaded", "orchestrated", "synergy", "synergies",
    "cutting-edge", "state-of-the-art", "best-in-class", "world-class", "seamlessly",
    "robust", "holistic", "paradigm", "game-changing", "groundbreaking", "transformative",
    "pivotal", "testament", "meticulous", "delve", "underscore", "showcasing", "fostering",
]
SELF_SIGNIFICANCE = re.compile(
    r",?\s*(demonstrating|showcasing|highlighting|underscoring|reflecting|illustrating|"
    r"exemplifying|solidifying)\s+(my|a|an|the|strong|exceptional|significant)\b", re.I)
NOT_JUST_X_BUT_Y = re.compile(r"\bnot\s+(just|only|merely)\b[^.]{0,80}?\bbut\b", re.I)
COPULA_AVOIDANCE = re.compile(r"\b(serves?\s+as|stands?\s+as|functions?\s+as|acts?\s+as)\b", re.I)
RULE_OF_THREE = re.compile(r"\b\w+,\s+\w+,?\s+and\s+\w+\b")
EM_DASH = re.compile(r"[—–]")


# A line that starts a new bullet, rather than continuing the previous one.
_BULLET_START = re.compile(r"^\s*(?:[-\u2022*\u00b7\u25aa\u25cf\u2013]|\d+[.)])\s+")
# A line that ends where a thought ends, rather than at the edge of the page.
_ENDS_COMPLETE = re.compile(r"[.!?;:]\s*$|^\s*$")


def _bullets(text: str) -> list[str]:
    """Reconstruct bullets from PDF text, rejoining lines that were wrapped by layout.

    This is a correctness fix, not tidying. Splitting naively on newlines treats every
    page-width wrap as a separate bullet, so a PDF that wraps at a narrow column yields many
    near-identical fragment lengths and an artificially LOW length variance. Measured on 60
    real resumes against LLM rewrites of the same resumes, that artefact was the single
    "strongest" signal in the whole detector - human median variance 0.40 vs 0.66 for rewrites -
    and it was measuring column width. A candidate would have been flagged for how their PDF
    happened to wrap.

    A line continues the previous one when it does not begin a bullet, the previous line did
    not end at a sentence boundary, and the previous line looks long enough to have been cut
    off by the page rather than by the writer.
    """
    raw = text.splitlines()
    merged: list[str] = []
    for line in raw:
        stripped = line.strip()
        if not stripped:
            continue
        starts_new = bool(_BULLET_START.match(line)) or not merged
        prev_complete = bool(_ENDS_COMPLETE.search(merged[-1])) if merged else True
        prev_short = len(merged[-1].split()) < 8 if merged else True
        if starts_new or prev_complete or prev_short:
            merged.append(_BULLET_START.sub("", stripped))
        else:
            merged[-1] = f"{merged[-1]} {stripped}"
    return [b for b in merged if len(b.split()) >= 4]


def _flag(pattern_id: str, description: str, quote: str, confidence: float) -> Flag:
    return Flag(pattern_id=pattern_id, description=description,
                span=Span(text=quote[:200]), confidence=confidence)


def read_style(text: str) -> StyleRead:
    words = text.split()
    bullets = _bullets(text)
    flags: list[Flag] = []

    if len(words) < config.MIN_WORDS_FOR_STYLE_SCORE:
        return StyleRead(
            score=0.0, band="low", patterns_fired=[], word_count=len(words),
            caveat=(f"Not scored: {len(words)} words is below the {config.MIN_WORDS_FOR_STYLE_SCORE}-word "
                    f"floor at which style analysis means anything. Reported as no signal, not as clean."),
        )

    low = text.lower()

    stock_hits = [p for p in STOCK_PHRASES if re.search(rf"\b{re.escape(p)}\b", low)]
    if len(stock_hits) >= 3:
        flags.append(_flag("stock_phrases",
                           f"{len(stock_hits)} stock phrases clustered: {', '.join(stock_hits[:6])}",
                           ", ".join(stock_hits[:6]), min(1.0, len(stock_hits) / 8)))

    for m in list(SELF_SIGNIFICANCE.finditer(text))[:3]:
        flags.append(_flag("self_significance",
                           "a bullet explains its own significance instead of stating what happened",
                           text[max(0, m.start() - 90):m.end() + 20], 0.5))

    if len(NOT_JUST_X_BUT_Y.findall(text)) >= 2:
        m = NOT_JUST_X_BUT_Y.search(text)
        flags.append(_flag("negative_parallelism",
                           f"'not just X, but Y' used {len(NOT_JUST_X_BUT_Y.findall(text))} times",
                           text[m.start():m.start() + 120] if m else "", 0.55))

    if (n := len(COPULA_AVOIDANCE.findall(text))) >= 2:
        flags.append(_flag("copula_avoidance", f"'serves as' / 'stands as' used {n} times, where 'is' would do",
                           COPULA_AVOIDANCE.search(text).group(0), 0.4))

    # Rhythm: LLM-written bullets tend to be unusually uniform in length. Needs enough bullets
    # for a standard deviation to mean anything.
    if len(bullets) >= 6:
        lengths = [len(b.split()) for b in bullets]
        mean = statistics.mean(lengths)
        cv = statistics.pstdev(lengths) / mean if mean else 1.0
        if cv < 0.22:
            flags.append(_flag("uniform_rhythm",
                               f"{len(bullets)} bullets almost identical in length "
                               f"(mean {mean:.0f} words, variation {cv:.0%})",
                               bullets[0], 0.45))
        if sum(1 for b in bullets if RULE_OF_THREE.search(b)) / len(bullets) > 0.5:
            flags.append(_flag("rule_of_three",
                               "more than half of all bullets use an X, Y and Z triple",
                               next(b for b in bullets if RULE_OF_THREE.search(b)), 0.4))

    if (n := len(EM_DASH.findall(text))) >= 5:
        flags.append(_flag("em_dash_density", f"{n} em dashes - unusual in a hand-written resume",
                           "—", min(0.5, n / 20)))

    # Confidence-weighted, saturating rather than additive: five weak signals should not add up
    # to a certainty. Divisor chosen so ~3 mid-confidence patterns lands mid grey band.
    score = min(1.0, sum(f.confidence for f in flags) / 3.2)
    lo, hi = config.STYLE_GREY_BAND
    band = "low" if score < lo else ("high" if score > hi else "grey")

    return StyleRead(
        score=round(score, 3), band=band, patterns_fired=flags, word_count=len(words),
        caveat=("Advisory only - this signal never contributes to a flag. We measured it on 60 "
                "real resumes against LLM rewrites of the same resumes: the strongest pattern "
                "separated the two classes for only 27% of rewrites, and most separated for "
                "under 8%. Published work also finds a 61% false-positive rate for non-native "
                "English writers. Read it as a prompt to look at the document yourself, never "
                "as a finding about the person."),
    )
