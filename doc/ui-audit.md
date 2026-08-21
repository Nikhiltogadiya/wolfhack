# Full UI audit, 2026-08-21

Every page, every control, every state. Appended to as things are found; nothing removed.
Severity: **P0** broken or wrong · **P1** confusing or missing · **P2** polish.

## Found so far

| # | Sev | Page | Problem |
|---|---|---|---|
| A1 | P0 | candidate detail | Header is broken: name wraps to two lines, the subtitle collapses to one word per line, and the four score cards overlap it and run off the right edge |
| A2 | P2 | role page, job detail | A very long role title produces a 225px-tall heading (5–6 lines). No overflow, but ugly. Needs `line-clamp` |

## Verified working (tested, not assumed)

- **No dead links.** 28 distinct internal link targets across 16 pages, all resolve.
- **No orphan buttons.** Every `<button>` is inside a form or has a handler.
- **All form actions resolve** to real routes.
- **Zero horizontal overflow** on all 17 pages at 1400px, and at 1024px.
- **Empty states** render properly: a role with no candidates shows "No CVs yet"; integrity
  shows "0 documents passed with nothing hidden".
- **Compare rejects bad input** (`?ids=` empty, one id, four ids, non-existent ids) with 400
  and a message rather than a crash.
- **Apply validates** — missing name, bad email, missing CV each give a specific message and
  keep what was typed.
- **Long titles** do not break any layout.
