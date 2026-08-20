"""Third-party code, vendored with attribution. Do not edit these files in place.

`hcd.py` — Hidden Content Detection, from UNITES-Lab/resume-injection-measurement (MIT, see
LICENSE.hcd). Released with "Prompt Injection in Resumes" (USENIX Security 2026; Duke/UNC/
Berkeley + hireEZ), which measured 196,682 real resumes. Four detection methods per text span:
tiny font, colour distance to background, visual variance, and phantom-ink density.

Vendored rather than pip-installed because the upstream project ships no release, and we need
to call one function rather than its CLI.

ONLY LOCAL CHANGE from upstream: `import fitz` -> `import pymupdf as fitz`, because the bare
`fitz` alias is deprecated in PyMuPDF 1.28 and emits a warning on every import. Nothing else is
touched, so a future upstream version can be diffed cleanly. Our own additions - cross-engine
divergence, which covers the off-page case HCD misses - live in ../ingest/forensics.py.
"""
