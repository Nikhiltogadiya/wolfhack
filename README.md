# Fit Happens

Ranks who **fits** the role. Flags who **isn't real**. Never decides.

An applicant-screening layer built for the Akkodis *Talent & Opportunity Marketplace*
challenge. Two components that are kept apart by design:

- **Fit Engine** — maps résumé claims to a role's requirements and scores that mapping alone.
  Writing quality cannot move this number. A flat résumé from the right person outranks a
  polished one from the wrong person.
- **Slop Bouncer** — flags AI-written and unsupported claims. Its strongest possible output is
  *flag for human review*. It has no reject path, structurally.

Plus **GitHub verification** (claims checked against real commit history — including *undersold*
evidence the CV forgot to mention) and a **JD slop scan** that holds the employer's own job ad
to the same standard.

## Quickstart

```bash
uv sync --all-extras
export NVIDIA_API_KEY=...        # required
export GITHUB_TOKEN=...          # optional; 60 req/h without it
uv run uvicorn fit_happens.web.app:app --reload --port 8000
```

Tests: `uv run pytest` (network tests are opt-in: `uv run pytest -m live`).

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
