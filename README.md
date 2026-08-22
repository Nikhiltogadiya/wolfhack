# Fit Happens

**Start here:** [`doc/architecture.md`](doc/architecture.md) — the whole design with
diagrams. [`doc/demo-script.md`](doc/demo-script.md) — the demo, beat by beat.

Ranks who **fits** the role. Flags who **isn't real**. Never decides.

An applicant-screening layer built for the Akkodis *Talent & Opportunity Marketplace*
challenge. Two components that are kept apart by design:

- **Fit Engine** — maps résumé claims to a role's requirements and scores that mapping alone.
  Writing quality cannot move this number. A flat résumé from the right person outranks a
  polished one from the wrong person.
- **Slop Bouncer** — flags AI-written and unsupported claims. Its strongest possible output is
  *flag for human review*. It has no reject path, structurally.

Plus **external verification** — GitHub commit history, certifications checked against how
their issuers actually name them, publications via OpenAlex, and document recency — and a
**job-ad scan** that holds the employer's own advert to the same standard it holds candidates.

It is two-sided. Candidates get their own view at `/apply/{token}`: where their application
stands, **which sources they allow us to look at** (everything external is off until they turn
it on, and the fetch does not happen without it), what we read from their CV with the exact
lines cited, what we noticed and want to ask about, and the questions themselves. Their answers
feed checkpoint 3.

## Quickstart

```bash
uv sync --all-extras

export OPENROUTER_API_KEY=...          # primary model provider
export NVIDIA_API_KEY=...              # optional; automatic fallback if the primary errors
export GITHUB_TOKEN=...                # optional; 60 requests/hour without it
export FIT_HAPPENS_TEAM_PASSCODE=...   # optional; without it the hiring pages are open
                                       #   and say so in a banner on every page

uv run uvicorn fit_happens.web.app:app --port 8000
```

Open http://127.0.0.1:8000, choose the employer door, create a role by pasting a job advert,
and upload some CVs.

**Do not add `--reload`.** The reloader restarts on any file change and kills in-flight upload
processing, leaving the page waiting on work that is never coming back.

Tests: `uv run pytest` — 380 of them, no network needed.

## Demo data is not in the repo

`data/` holds application records: candidates, uploaded CVs, consent decisions, stages and
answers. That is real application data even when the applicants are invented, so it stays on
the machine running the app and is never committed.

To get something to look at, either upload a few CVs through the interface, or generate a set:

```bash
uv run python tools/make_applicant_cvs.py   # ten fictional applicants
uv run python tools/make_demo_cv.py         # one with defects built in, for the detectors
```

Then create a role and upload them. A CV takes one to three minutes the first time and is
cached afterwards, so a re-run is instant. `FIT_HAPPENS_OFFLINE=1` forces cache-only and
fails loudly on a miss, which is how you prove a demo needs no network.

## What we measured

| | |
|---|---|
| Injection detection | 0 false positives on 60 real resumes; catches white-on-white and 0.6pt text |
| Cost | $0.0048 per candidate |
| Style detection (CP1) | **0% detection at 0% false positives** on 60 real resumes vs LLM rewrites of the same resumes |

That last number is deliberate and we report it. The brief's four "vibe check" patterns
separate the two classes for under 8% of cases; the only signal that works at all is em-dash
density, at 27%, and the threshold that buys it costs flagging one real person in ten. So
style stays advisory and is structurally barred from producing a flag. See
`scripts/calibrate.py` and `scripts/feature_analysis.py`.

## Documentation

| File | What |
|---|---|
| `CLAUDE.md` | The hard rules. Read before changing anything. |
| `doc/project-brief.md` | Canonical spec, milestones, demo script |
| `doc/engineering-log.md` | What was tried, what failed, why |
| `doc/backlog.md` | What we still owe |
| `doc/source/` | Dated raw record — local only, not published (client material) |

## The one thing to understand

The separation between fit and slop is enforced by **type signatures and tests**, not by
convention. `FitEngine`'s input types carry no style fields, the slop verdict enum has no reject
variant, and "likely fabricated" requires two independent flags with distinct evidence spans.
Those are the invariants in `tests/test_invariants.py` — they are the product, not decoration.

## Licence

**AGPL-3.0-or-later.** See [LICENSE](LICENSE), and [NOTICE](NOTICE) for why.

The short version: this project uses PyMuPDF, which is AGPL-3.0 or a paid Artifex licence, both
as the primary PDF text extractor and as the foundation of the hidden-content detector. AGPL is
strong copyleft, so the whole work is AGPL-3.0. If you run a modified version as a network
service, you must offer your users its source.

Third-party components and their licences are listed in [NOTICE](NOTICE). The vendored hidden
content detector is MIT, from
[UNITES-Lab/resume-injection-measurement](https://github.com/UNITES-Lab/resume-injection-measurement),
with its licence at `src/fit_happens/vendor/LICENSE.hcd`.
