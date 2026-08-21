# Full UI audit, 2026-08-21

Every page, every control, every state. Appended to as things are found; nothing removed.
Severity: **P0** broken or wrong · **P1** confusing or missing · **P2** polish.

## Found so far

| # | Sev | Page | Problem |
|---|---|---|---|
| A1 | P0 | candidate detail | Header is broken: name wraps to two lines, the subtitle collapses to one word per line, and the four score cards overlap it and run off the right edge |
| A2 | P2 | role page, job detail | A very long role title produces a 225px-tall heading (5–6 lines). No overflow, but ugly. Needs `line-clamp` |
| A3 | P1 | ranking | Ticking a third compare box left the button reading "Compare 3/2" and **disabled**, with nothing saying why. Now capped at two — the third tick drops the oldest and the button stays live |
| A4 | P2 | ranking | The bulk-staging form was built by interpolating candidate ids into an `innerHTML` string; an id containing a quote would rewrite the form. Now built from DOM nodes |
| A5 | P3 | ranking | The explainer's "Got it" had no `type`, so it defaulted to `type=submit`. Harmless outside a form, but wrong. Now `type="button"` |
| B1 | **P0** | `/jobs/{slug}/apply` | **The apply button was dead.** The CV input is `required` *and* `class="hidden"`. Chrome cannot anchor a validation bubble to a `display:none` control, so an applicant who forgot the CV pressed "Send my application" and **nothing happened at all** — no submit event, no message, no tooltip. Verified live before and after. Fixed with `sr-only` (invisible but rendered and focusable); the bubble now reads "Please select a file." |
| B2 | **P0** | ranking | Stray unmatched `</form>` — form depth traced to −1 at line 43. Deleted |
| B3 | **P0** | ranking | Empty-state row spanned `colspan="6"` against **7** `<th>`, leaving "No CVs yet" left-shifted with a stray 7th cell. Now 7 |
| B4 | **P0** | ranking | The same header bug as A1, still live here: title block had no `min-w-0` against a `shrink-0` button cluster, so it was crushed and the row overflowed below ~1090px. Now wraps |
| B5 | P1 | ranking | Flipping "Internal JD" **silently discarded the recruiter's sort and filter** — the GET form carried only `internal`. Now carries `sort` and `filter_by` too |
| B6 | P1 | ranking | "3 internal criterio**na** was rejected" — the plural of *criterion* built by appending `a`. Now "criteria were" |
| B7 | P1 | ranking, role step 2 | `+ Upload CVs` is a `display:none` file input — the page's primary action, unreachable by keyboard. Now `sr-only` |
| B8 | P1 | ranking | Candidate name was `whitespace-nowrap` with no cap, so one long name widened the table and squeezed the four score columns. Now `truncate` + `title` |
| B9 | P1 | injection | The injected adversarial text renders in `font-mono` with no wrap control — the likeliest 300-char unbroken token on the site. Now `break-all overflow-x-auto` |
| B10 | P1 | candidate portal | Consent history looked up `scopes[e.scope].label` against the *current* scope dict; the `community` scope was removed in a0a135c, so an old entry rendered as an empty string. Now falls back to the raw scope name |
| B11 | P2 | processing | Dead empty anchor building a URL from the role **title** where the slug belongs. Deleted |
| B12 | P2 | apply | A long CV filename replaced the hint text with no width constraint. Now `max-w-full break-all` |

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
