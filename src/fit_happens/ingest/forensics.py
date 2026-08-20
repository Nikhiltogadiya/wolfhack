"""Ingest a resume and produce a Document whose text is safe to prompt with.

Two independent detectors, because they fail in different places:

* **HCD** (vendored, USENIX Sec '26) inspects every span for tiny fonts, colour-matched-to-
  background fill, flat visual regions, and phantom ink. Strong on *visually* hidden text.
* **Cross-engine divergence** catches text that is in the file but outside the visible page,
  which HCD does not look for and PyMuPDF cannot even extract. See divergence.py.

The output contract that matters: `Document.text` has every hidden span removed before the
object exists, so no downstream stage can accidentally feed an injected instruction to a model.
That is asserted by tests/test_ingest.py::test_injection_never_reaches_prompt.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

from ..schemas import Document, HiddenFinding, Span
from . import divergence, extract, sanitize


def _hcd_findings(path: str) -> list[HiddenFinding]:
    """Run the vendored detector and translate its output into our types.

    Uses the SECOND return value (`positions`), not the first. Both describe the same
    detections, but `detections` carries only {excerpt, explanation} while `positions` also
    carries page, bbox and a debug string with the measured font size / colour distance - which
    is what makes the dashboard able to say *why* rather than just *that*.
    """
    if not path.lower().endswith(".pdf"):
        return []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from ..vendor import hcd

            _detections, positions, _timing = hcd.analyze_pdf_content(path)
    except Exception:
        return []

    known = {"tiny_font", "solid_color_block", "low_variance", "phantom_text_no_ink", "zero_width_chars"}
    out: list[HiddenFinding] = []
    for d in positions or []:
        excerpt = (d.get("excerpt") or "").strip()
        if not excerpt:
            continue
        explanation = d.get("explanation") or ""
        method = next((m for m in known if m in explanation or m in str(d.get("debug", ""))), "solid_color_block")
        page = d.get("page")  # HCD reports 1-indexed; Span stores 0-indexed
        page0 = (page - 1) if isinstance(page, int) and page > 0 else None
        bbox = d.get("bbox")
        out.append(
            HiddenFinding(
                method=method,  # type: ignore[arg-type]
                excerpt=excerpt[:400],
                span=Span(text=excerpt[:400], page=page0, bbox=tuple(bbox) if bbox else None),
                provenance=_provenance(method, page0, str(d.get("debug", "")), bbox),
            )
        )
    return out


def _provenance(method: str, page0: int | None, debug: str, bbox=None) -> str:
    """Plain-English why, for the dashboard. A recruiter has to be able to read this."""
    where = f"page {page0 + 1}" if page0 is not None else "the document"
    base = {
        "tiny_font": f"text too small to read, {where}",
        "solid_color_block": f"text coloured to match its background, {where}",
        "low_variance": f"text on a flat block of identical colour, {where}",
        "phantom_text_no_ink": f"text extracts from {where} but leaves no ink when rendered",
        "zero_width_chars": f"invisible characters embedded in the text, {where}",
    }.get(method, f"hidden text, {where}")

    # Surface the measured numbers HCD already computed - "0.5pt" is far more convincing to a
    # judge than "tiny font", and it is evidence rather than a label.
    measured = []
    for key, label in (("font_size", "pt"), ("color_distance", " colour distance"), ("ink_density", " ink")):
        m = re.search(rf"{key}=([0-9.]+)", debug)
        if m:
            measured.append(f"{m.group(1)}{label}")
    # HCD's debug string does not carry the font size, but the span's own height is a direct
    # proxy for it - and "0.6pt" is far more convincing evidence than the words "tiny font".
    if method == "tiny_font" and bbox and not measured:
        height = float(bbox[3]) - float(bbox[1])
        if height > 0:
            measured.append(f"{height:.1f}pt tall")
    if "std_dev=0.0" in debug and not measured:
        measured.append("zero pixel variance")
    return f"{base} ({', '.join(measured)})" if measured else base


def ingest(path: str | Path) -> Document:
    path = str(path)
    views = extract.extract_all(path)
    raw = extract.primary_text(views)

    hidden = _hcd_findings(path)
    div_findings, div_score = divergence.detect(views)
    hidden.extend(div_findings)

    for h in hidden:
        h.looks_like_instruction = sanitize.looks_like_instruction(h.excerpt)

    # Anything hidden is removed from the text the model will see, whether or not it parsed as
    # an instruction. Hidden-but-benign is still not something a candidate should get credit
    # for, and "benign" is a judgement we would rather not have to make correctly every time.
    clean = sanitize.excise(raw, [h.excerpt for h in hidden])

    return Document(
        source_path=path,
        text=clean,
        raw_text=raw,
        hidden=hidden,
        engine_chars={k: len(v) for k, v in views.items()},
        divergence=div_score,
    )
