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
| C1 | **P0** | every candidate page | **Shortlist / Start reviewing saved the stage, then showed a 404.** `set_stage` redirected to `/role/{slug}/c/{cid}` — a pre-`/hiring` path — and the only form that posts there sends no `back`, so the broken fallback fired every time. The most visible break in the recruiter flow |
| C2 | **P0** | 8 `/hiring` routes | **No auth gate at all**: upload, seed, set-stage, record-pass, clear-flags, dismiss, status, check-internal. Six of them mutate state. They were exactly the eight written without a `request` parameter, so `auth.require` was impossible to call and got dropped. Fixed with one middleware on the prefix rather than eight prologues — a ninth route cannot now be added ungated. Verified: all eight redirect to sign-in |
| C3 | **P0** | `/hiring/sign-in` | Open redirect — `next` went straight into `RedirectResponse`. `?next=https://evil.example` left the site; `//evil.example` did too (a browser reads it as protocol-relative). Both now fall back to `/hiring` |
| C4 | **P0** | `/apply/{token}` consent | **Granting a scope did nothing.** Consent was read only inside `run_candidate`, which had finished hours before the candidate touched the toggle. The pill flipped to SHARING, the audit line was written, and no repo or paper was ever fetched. Now schedules `tasks.reverify`, which re-runs only the verify step (re-scoring would let an external source move a number it must never move) |
| C5 | **P0** | error page | `error.html` extends the **recruiter** base, and `_err` is called from public routes. A candidate with a dead link saw the hiring sidebar and, with no passcode set, the "this area is unprotected" banner. Split into `error_public.html`; the shell is now chosen from the request path, not from `back` |
| C6 | P1 | `/apply/{token}` | An expired link redirected the candidate to `/hiring` — the recruiter dashboard. Now a public 404 |
| C7 | P1 | `/apply/{token}/consent` | An unknown or locked scope saved and redirected identically to a real one — a silent no-op. Now 400 |
| C8 | P1 | 5 error pages | "Go back" pointed at pre-`/hiring` paths and 404'd |

### The test that should have caught C4

`test_every_consent_scope_actually_changes_behaviour` greps `n_verify`'s **source** for
`allows("github")`. That answers *does this string appear*, not *does granting change
anything* — so it passed throughout the release in which granting did nothing at all.
Replaced with two tests that exercise the route: one asserts a grant schedules the fetch for
that candidate, one asserts a revoke schedules nothing. **Verified by reinstating the bug:
the new test fails, and passes again once fixed.**
| D1 | **P0** | ranking chips | **"Needs a human" selected on writing style.** The filter read `cp2.verdict == flag_for_human or c.style.band != "low"`, so a CV that merely reads as polished, with zero authenticity flags, was put in front of a reviewer on prose alone. Hard rules 3 and 9 are enforced all the way through the engine and were handed straight back in the one surface a recruiter acts on — and the style signal is the one measured at 0% detection. Predicate extracted as `needs_a_human()` and tested against candidates |
| D2 | P1 | 5 modules | The style-pattern id list was hand-copied into **four** places and **two had already drifted**, silently dropping `style_divergence`. CP3-only today, so nothing had broken yet — the next pattern added to one copy would have put a style flag into the bluff count, which is what hard rule 2 exists to prevent. One `frozenset` in `schemas.py` now; the template dropped its copy entirely for `c.authenticity_flags`, which already applied that filter. Guarded by a test that catches the *next* unregistered pattern, not this one |
| D3 | P1 | `/apply/{token}` | Consent withdrawal globbed every `gh_*.json` in the shared cache, so **one candidate revoking deleted every other candidate's cached lookups**, in every role — while leaving their own `verifications` rows in place. Both too broad and incomplete. Now `github.forget()` / `publications.forget()` delete only that CV's keys |
| D4 | P1 | `/apply/{token}` | **Permanent spinner.** `tasks.recent` is a ring buffer of 8 that the recruiter's "Dismiss" button empties. Once a candidate's task fell off it, the page had no state, decided the work was still running, and reloaded every 6 seconds forever on an application that had already failed. Third state added, keyed on time since applying |
| D5 | P1 | `/apply/{token}` | An **all-blank submission counted as answering**: it set `submitted_at`, replaced the form with a summary the candidate could never reopen, and scored LOW RISK response authenticity for answers nobody wrote. Now refused with a message, form kept |
| D6 | P1 | role step 2 | Unticking **every** requirement kept **every** requirement — `if keep:` read an empty set as "touched nothing". The control inverted at exactly the boundary that matters |
| D7 | P1 | landing | "Browse N open roles" counted closed ones; `/jobs` excluded them, so the number never matched the list |
| D8 | P1 | `/hiring/market` | A missing or malformed `snapshot.json` made `"{:,}".format(None)` raise — a **500 on the whole page**, one `rm` away. Defaults to 0. Verified by moving the file aside |
| D9 | P2 | candidate portal | Question labels had no `for`/`id`, so clicking one focused nothing |
| E1 | **P0** | consent records | A scope removed from `SCOPES` but still on disk made `summary()` raise `KeyError` and **500 the candidate's own portal**. Two live demo records still carry `"community": false` — latent only because it is false. Retired scopes are now pruned on load, so nothing downstream has to know it happened |
| E2 | P1 | tasks | **A mistyped URL created a role directory.** `tasks._path` called `mkdir` on every access including reads, reintroducing exactly what `store.Run`'s docstring says was fixed there. Verified: two bogus slugs created two directories. Now only `_write` creates, `clear_finished` no-ops when there is nothing to clear, and both routes 404 on an unknown role |
| E3 | P1 | all three upload sites | `accept=".pdf,.docx,.txt"` is a **file-picker hint, not a constraint**. The public apply endpoint took any file type, streamed unbounded bytes to disk with `copyfileobj`, then started a paid LLM pipeline per file. Now one bounded helper: type allowlist, 10 MB cap, empty-file check. An oversized file is **deleted rather than truncated** — a truncated CV would be scored as if it were the whole document. Verified end to end with a `.sh`, a 12 MB file and an empty one |
| F1 | P1 | every recruiter page | The sidebar is a fixed 208px rail, so a 375px screen left **167px** for the page — every recruiter page overflowed regardless of what the page did. Fixed once in `base.html`: below `md` the rail becomes a top nav. Cheaper and more correct than a per-page workaround |
| F2 | P1 | ranking | The Internal-JD button and its 170px caption sat in a no-wrap flex row and pushed 179px past the viewport. Now wraps; caption hidden below `sm` |
| F3 | P1 | pills (all pages) | The `pill()` macro had no `whitespace-nowrap`, so "NOT CORROBORATED" wrapped **inside the pill**, onto two lines — visible on the ranking table at full desktop width. A pill whose own label wraps reads as a broken component |
| F4 | P1 | 9 templates | Missing `min-w-0` / `shrink-0` / responsive grid breakpoints: role titles crushed their pills, a hard `grid-cols-4` held a CV filename, the candidate portal's 4-step progress bar (the one page applicants open on a phone) wrapped labels to three lines |
| F5 | P2 | ask | The link row could not wrap; the "Their link" and "A message you can send" captions were `<div>`s, not `<label>`s, so clicking them focused nothing |
| F6 | P2 | ask, candidate | `target="_blank"` with no `rel="noopener noreferrer"` |

**Final sweep: 72 page/width combinations across 18 pages at 375 / 768 / 1280 / 1600 — no page
body scrolls horizontally anywhere.** Screenshotted at 375px as well as measured, because
"no overflow" is not the same as "looks right": that check is what caught F3 and the collapsed
sub-nav sitting beside its siblings instead of on its own row.
| G1 | P1 | candidate detail | **Evidence rows vanished after a role edit.** The skill map iterated the candidate's *matches* and dropped any whose `requirement_id` no longer existed — and requirement ids are positional (`ext-0..N`), so editing a role re-parses the advert and renumbers them. A candidate scored before the edit lost rows from the one table whose stated promise is *"every score traces to a line in the résumé"*, while the header above still showed their old fit score. Now iterates the **requirements**, so the table always lists what the role asks for and names which ones this CV was not scored against. Verified on a throwaway copy: 6 of 17 matches now renders 17 rows and 11 explicit notices, where it used to render 6 |
| G2 | P1 | role create / edit | `parse_jd` — a blocking network round trip — ran directly inside three `async def` routes, **freezing every other request in the process** for its duration, applicants mid-application included. Now through `run_in_threadpool` |
| G3 | P2 | candidate detail | With no preferred requirements, a bare "PREFERRED SKILLS · COVERAGE · GAP · EVIDENCE" header rendered over nothing. Now the block is skipped |

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
