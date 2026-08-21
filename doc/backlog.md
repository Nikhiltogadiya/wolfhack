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
| 15 | DONE 2026-08-21 | Recruiter rejection feedback | Fixed reasons mapped to what each would change, captured at the moment of the decision | `feedback.py`, `/market` | - |
| 16 | WONTFIX | Candidate pain: fragmented signals | Employer reviews, financials, news. Checked JobDataLake's `get_company`: industry and size only. Every other source is paid or needs scraping. **Said on stage, not faked.** | - | A real data source appears |
| 17 | DONE 2026-08-21 | Candidate pain: blind discovery | Was right to defer until a corpus existed. JobDataLake gave one: 47 postings of a single Speechify job; 75% of a 67-posting sample redundant | `jd/discovery.py`, `/market` | - |
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

| 45 | DONE 2026-08-21 | Looking up a role created it | `Run.__init__` called mkdir, so /role/typo brought an empty role into existence. Created on first write now | `store.py` | - |

## Redesign delivered, 2026-08-21

| # | Status | Item | Side |
|---|---|---|---|
| R1 | DONE | First-run screen explaining the product | recruiter |
| R2 | DONE | Role creation in two steps, with a requirements preview she can edit before committing | recruiter |
| R3 | DONE | Drag-and-drop upload, formats stated, per-file progress | recruiter |
| R4 | DONE | Dismissible explainer for the four scores | recruiter |
| R5 | DONE | Sort on any column; filters for undecided / needs-a-human / top fit / waiting | recruiter |
| R6 | DONE | **Compare two candidates side by side**, divergences first | recruiter |
| R7 | DONE | Decision bar: Ask questions / Start reviewing / Shortlist / Pass | recruiter |
| R8 | DONE | Stages, so the product models progression and not only rejection | recruiter |
| R9 | DONE | "Ask questions" sets the stage and produces a link, a preview and a written message | recruiter |
| C1 | DONE | One clear task at the top of the portal | candidate |
| C2 | DONE | Reordered: action, then transparency, then consent | candidate |
| C3 | DONE | Answer progress, drafts saved in-browser, confirmation after sending | candidate |
| 46 | DONE | One stalled chunk failed the whole CV | Retried once, then fails loudly. Silently dropping it would lose claims without saying so |
| 47 | DONE | Stale upload failures sat at the top of the page forever | Dismissible |

## Candidate entry, 2026-08-21

Found by opening the site as a candidate instead of curling it.

| # | Status | Item |
|---|---|---|
| 48 | DONE | **`/` was the recruiter dashboard.** A candidate landed on other applicants' names, fit scores and flags. Every `/role/...` page answered 200 with no credentials. |
| 49 | DONE | Split landing: candidate or employer |
| 50 | DONE | Public job board with our clarity read of each advert |
| 51 | DONE | Job detail: advert, requirements, what it does not tell you |
| 52 | DONE | **Apply** - name, email, CV. There was no way to apply at all |
| 53 | DONE | Their own page immediately, including a real "still reading your CV" state |
| 54 | DONE | `/track` recovers a lost link by email |
| 55 | DONE | Applicants are people, not filenames - one appeared as `15118506` |
| 56 | DONE | Hiring area behind a shared passcode, with a visible banner when unset |
| 57 | DEFERRED | Real per-user auth with a record of who viewed which application | The passcode is honest about not being this. A subject access request asks exactly "who looked at my file", and we cannot answer it |
| 58 | DEFERRED | Email delivery of the application link | Copy/paste today; needs an SMTP provider |

## Employer walkthrough, 2026-08-21

Signed in as a recruiter and used it. What is wrong, in the order it hurts.

### Identity — visible and embarrassing
| # | Status | Problem |
|---|---|---|
| 59 | DONE | An applicant shows as **"Naledi Dube 7B4F54"** — the id hash leaks into the display name |
| 60 | DONE | CVs added from the dashboard show as **"15118506"**, a filename. The pipeline names a candidate after the file even when an application carries a real name |

### Workflow — things a recruiter needs and simply cannot do
| # | Status | Problem |
|---|---|---|
| 61 | DONE | **Cannot edit a role.** A typo in the advert means deleting and starting again |
| 62 | DONE | **Cannot close a filled role.** It sits under "Open roles" forever, and candidates keep applying |
| 63 | DONE | **Cannot remove a candidate** — a duplicate application or a wrong file is permanent |
| 64 | DONE | **No bulk actions.** Shortlisting five people is five page loads |
| 65 | DONE | "Roles" in the nav goes to *create new*, not a list of roles |

### Awareness — she has to keep checking
| # | Status | Problem |
|---|---|---|
| 66 | DONE | Nothing tells her a candidate has **answered**. She asked, and now must revisit the page to find out |
| 67 | DONE | Overview "strongest matches" shows no stage, so someone already shortlisted looks identical to someone untouched |

### Layout
| # | Status | Problem |
|---|---|---|
| 68 | DONE | Stage pill clipped — "SHORTLI…" |
| 69 | DONE | Candidate column too narrow; names wrap to three lines |

| 70 | DONE | `.env` was created with the passcode and nothing read it — the hiring area stayed open while it looked configured. `config.py` now loads `.env` (shell wins), and `.env` is gitignored |
| 71 | DONE | Widening the ranking table pushed the Stage column off-screen. Fixed by giving the table more of the row and tightening the rail, verified by measuring rather than eyeballing |
