# Backlog

What we still owe. One line per item, added **at the moment of deferral**.
Status: `DEFERRED` (do later) · `UNVERIFIED` (claimed, not confirmed) · `BLOCKED` (waiting on
someone) · `WONTFIX` (decided against, reason recorded) · `DONE` (with date).

| # | Status | Item | Why | Where | Trigger |
|---|---|---|---|---|---|
| 1 | DONE 2026-08-20 | Kaggle corpus | 2,484 real resume PDFs in place | `data/corpus/` | - |
| 2 | DONE 2026-08-20 | `GITHUB_TOKEN` | set; 5,000 req/h | env | - |
| 3 | DONE 2026-08-21 | Checkpoint 3 response scan | Needed a candidate surface, which now exists | `slop/response.py` | - |
| 4 | DONE 2026-08-21 | User-controlled sharing | Responsible AI now 6/6 | `candidate/consent.py` | - |
| 5 | DONE 2026-08-20 | Off-page text detection | Solved by cross-engine divergence, not a parser flag | `ingest/divergence.py` | - |
| 6 | DONE 2026-08-20 | Calibration (M10) | 60 real vs 60 rewrites; 0% FPR, 0% TPR | `scripts/calibrate.py` | - |
| 7 | DONE 2026-08-20 | Offline demo replay | Verified with `FIT_HAPPENS_OFFLINE=1` | - | - |
| 8 | DONE 2026-08-21 | Publications evidence | OpenAlex, free and keyless | `verify/publications.py` | - |
| 9 | DONE 2026-08-21 | Certification verification | recognised / unrecognised / malformed | `verify/credentials.py` | - |
| 10 | DONE 2026-08-21 | Stale talent data | Document recency + parse completeness | `verify/freshness.py` | - |
| 11 | WONTFIX | 'community' consent scope | Was declared and read by nothing. A consent control that does nothing is worse than an absent one. Needs scraping personal sites/forums | `candidate/consent.py` | A real fetcher exists |
| 12 | WONTFIX | Tune CP1 thresholds for detection | The only signal with separation (em dashes, 27%) costs ~10% false positives | `slop/style.py` | A non-perplexity signal with real separation appears |
| 13 | WONTFIX | Neural AI-text classifier as a scored signal | Liang et al: 61.22% FPR for non-native writers; mechanism is low perplexity | `slop/style.py` | - |
| 14 | WONTFIX | Voice, industry skill matching, cross-JD, SAP, Delta-module, closed-loop retraining | Killed in intake v0.1 §3 and §10 triage | - | Recorded so they do not creep back |
| 15 | DEFERRED | Recruiter rejection feedback | ~20 min (textarea + storage). No demo payoff, but answers "how does this improve?" | `web/` | Spare time before judging |
| 16 | DEFERRED | Candidate pain: fragmented signals | Employer reviews, financials, news. Needs paid or scraped sources we do not have | new module | A data source exists |
| 17 | DEFERRED | Candidate pain: blind discovery | Near-duplicate detection across postings. We have one JD; over one posting it is theatre | new module | A corpus of live postings |
| 18 | DEFERRED | Swap PyMuPDF for pypdfium2 | PyMuPDF is AGPL; blocks permissive open-sourcing | `ingest/` | If this repo goes public |
| 19 | DEFERRED | Guard may over-block height/weight in safety contexts | Over-blocking EMPLOYER input is the safe failure mode; the refusal is logged and readable | `jd/guard.py` | A warehouse/field role is demoed |
| 20 | UNVERIFIED | NIM `top_logprobs` support | Would enable perplexity-based detection. Moot while we reject perplexity signals | - | - |
| 21 | UNVERIFIED | CPU latency of the injection classifier | No benchmark run; llm-guard was never wired in (HCD covers the PDF case) | - | If the demo feels slow |
| 22 | UNVERIFIED | Fraser "detectors need >=100 words" | Could not retrieve the paper; NBER cuts against it. Not used as a constraint | `doc/project-brief.md` | Someone gets the JAIR full text |
| 23 | UNVERIFIED | Undersold collapse leaks near-variants | 'uwsgi-nginx' survived beside 'nginx'; prefix collapse is crude | `verify/github.py` | If it looks noisy on stage |
| 24 | UNVERIFIED | Publications on our own demo data | The corpus is anonymised, so no name resolves. Verified live against a known author instead | `verify/publications.py` | A CV with a real name |

---

## UX audit, 2026-08-21

Done by opening the site as a first-time visitor rather than as its author. The finding that
matters: **the website is a read-only viewer over a run the CLI produced.** Every action that
makes this a product - upload a CV, create a role, set internal criteria - is a shell command.
A judge who opens it fresh is shown `uv run python scripts/build_demo.py`.

### P0 - a new visitor cannot use the product at all

| # | Status | Problem | Why it matters |
|---|---|---|---|
| 25 | DONE 2026-08-21 | No home page; `/` is a role *detail* page | There is no level above a single hard-coded role |
| 26 | DONE 2026-08-21 | Fresh visit shows a CLI command as the empty state | The first thing a judge sees is a terminal instruction |
| 27 | DONE 2026-08-21 | Cannot upload a CV | The product's core action is unavailable in the product |
| 28 | DONE 2026-08-21 | Cannot create a role or paste a JD | The JD is a file on disk |
| 29 | DONE 2026-08-21 | Internal criteria are hard-coded in `scripts/build_demo.py` | The guard refusing a protected characteristic is our best compliance story and cannot be shown live |
| 30 | DONE 2026-08-21 | Only one role can exist (`Run("demo")`) | Nothing in the UI implies a second role is possible |

### P1 - things that are broken or actively mislead

| # | Status | Problem | Why it matters |
|---|---|---|---|
| 31 | DONE 2026-08-21 | Nav active state hard-coded to the first item | Every page except the first highlights the wrong thing |
| 32 | DONE 2026-08-21 | "Clear flag" and "Send questions" are decorative | Same class as the dead consent toggle: controls that do nothing |
| 33 | DONE 2026-08-21 | No progress feedback while a CV processes | Takes 30-60s cold with no indication anything is happening |
| 34 | DONE 2026-08-21 | 404s return a bare unstyled paragraph | |
| 35 | DONE 2026-08-21 | No error state for an unreadable upload | |

### P2 - navigation and completeness

| # | Status | Problem |
|---|---|---|
| 36 | DONE 2026-08-21 | No roles list, no candidates list above a single role |
| 37 | DONE 2026-08-21 | Candidate portal link is buried on a detail page |
| 38 | DONE 2026-08-21 | Job-ad page never shows the advert it is scoring |
| 39 | DONE 2026-08-21 | No breadcrumbs; no way back up from a candidate |
| 40 | DONE 2026-08-21 | Narrow-viewport behaviour | Measured in a 1024px frame: every page fits with room to spare (-12px). The `lg:` breakpoints stack the side rails correctly. |
| 43 | DONE 2026-08-21 | Stuck uploads shown as running forever | uvicorn `--reload` kills in-flight background tasks; the state file survives so the page spun on work that was never coming back. `tasks.pending()` now reaps anything past 480s. **Do not demo with `--reload`.** |
| 44 | DONE 2026-08-21 | UI claimed a CV takes 30-60s | Measured 153s cold for a long CV. Copy corrected. |

### Carried forward

| # | Status | Item |
|---|---|---|
| 41 | WONTFIX | **Candidate pain: fragmented signals.** Checked `get_company` on the JobDataLake MCP - it returns industry and size only. No reviews, financials, news or culture data. Every other source is paid or requires scraping. Stated on stage rather than faked. |
| 42 | DONE 2026-08-21 | **Candidate pain: blind discovery.** Was WONTFIX until a corpus existed. 47 postings of one Speechify job; 75% of a 67-posting sample is redundant. `jd/discovery.py`, `/market`. |

**Candidate pains: 3 of 4 built** - generic job ads, transparency, blind discovery. Fragmented
signals is the one we do not build, and we say so.
