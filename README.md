# Fit Happens

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
export NVIDIA_API_KEY=...        # required
export GITHUB_TOKEN=...          # optional; 60 req/h without it
uv run uvicorn fit_happens.web.app:app --reload --port 8000
```

Then open http://127.0.0.1:8000 and click **Load the sample role** — or create your own,
paste an advert, and upload CVs. Everything works in the browser; the CLI is optional:

```bash
uv run python scripts/build_demo.py data/demo/resumes/*.pdf          # same thing, headless
FIT_HAPPENS_OFFLINE=1 uv run python scripts/build_demo.py data/demo/resumes/*.pdf  # no network
```

Do not add `--reload` when demoing: it kills in-flight upload processing.

Tests: `uv run pytest` (network tests are opt-in: `uv run pytest -m live`).

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
| `doc/source/` | Dated, immutable raw record |

## The one thing to understand

The separation between fit and slop is enforced by **type signatures and tests**, not by
convention. `FitEngine`'s input types carry no style fields, the slop verdict enum has no reject
variant, and "likely fabricated" requires two independent flags with distinct evidence spans.
Those are the invariants in `tests/test_invariants.py` — they are the product, not decoration.
