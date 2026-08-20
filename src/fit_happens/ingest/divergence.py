"""Cross-engine divergence: text one extractor sees and another does not.

This exists because of a measured result, not a hunch. On a reportlab fixture whose injected
text sits outside the page box, the string is physically present in the content stream and:

    pdfplumber  sees it        pymupdf     does not
    pdfminer    sees it        pypdfium2   does not

PyMuPDF's TEXT_MEDIABOX_CLIP flag is NOT the lever - clearing it changes nothing (four probes,
see doc/engineering-log.md). So off-page injection is invisible to a human *and* to PyMuPDF,
while being fully readable by the pdfminer-family extractors that many real ATS pipelines use.

The nice property: this is not an attack-specific heuristic. Any technique that makes one
parser disagree with another gets caught, including ones nobody has invented yet.
"""

from __future__ import annotations

import re

from ..schemas import HiddenFinding, Span

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
_MIN_RUN = 4  # consecutive unseen words before we call it hidden content, not tokenizer noise


def _norm(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def find_divergent_runs(views: dict[str, str], render_family: set[str], stream_family: set[str]) -> list[str]:
    """Word runs the stream-family engines agree on that the render-family engines never show."""
    stream_texts = [views[e] for e in stream_family if views.get(e)]
    render_texts = [views[e] for e in render_family if views.get(e)]
    if not stream_texts or not render_texts:
        return []

    render_vocab: set[str] = set()
    for t in render_texts:
        render_vocab.update(_norm(t))

    runs: list[str] = []
    for t in stream_texts:
        words = _WORD.findall(t)
        current: list[str] = []
        for w in words:
            if w.lower() not in render_vocab:
                current.append(w)
            else:
                if len(current) >= _MIN_RUN:
                    runs.append(" ".join(current))
                current = []
        if len(current) >= _MIN_RUN:
            runs.append(" ".join(current))

    # de-duplicate while keeping the longest form of each run
    runs.sort(key=len, reverse=True)
    kept: list[str] = []
    for r in runs:
        if not any(r in k for k in kept):
            kept.append(r)
    return kept


def detect(views: dict[str, str]) -> tuple[list[HiddenFinding], float | None]:
    from .extract import FAMILY

    render = {e for e, f in FAMILY.items() if f == "render"}
    stream = {e for e, f in FAMILY.items() if f == "stream"}
    runs = find_divergent_runs(views, render, stream)

    lengths = [len(v) for v in views.values() if v]
    divergence = None
    if len(lengths) > 1 and max(lengths):
        divergence = 1.0 - (min(lengths) / max(lengths))

    findings = [
        HiddenFinding(
            method="engine_divergence",
            excerpt=run[:400],
            span=Span(text=run[:400]),
            provenance=(
                f"{len(run.split())} words extracted by "
                f"{'/'.join(sorted(e for e in stream if views.get(e)))} but absent from "
                f"{'/'.join(sorted(e for e in render if views.get(e)))} - "
                "text present in the file but outside the visible page"
            ),
        )
        for run in runs
    ]
    return findings, divergence
