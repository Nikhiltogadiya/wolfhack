# Fit Happens — project memory

Akkodis hackathon build (~24h, solo). Ranks who **fits** a role; flags who **isn't real**.
Two components that must never contaminate each other: **Fit Engine** (matching) and
**Slop Bouncer** (detection).

## Read before touching anything
- `doc/architecture.md` — how the whole thing fits together, with diagrams. Start here.
- `doc/demo-script.md` — what to click, in order, and what not to claim.
- `doc/project-brief.md` — canonical spec, milestones, demo script.
- `doc/engineering-log.md` — what was tried, what failed, why. Append as you go.
- `doc/backlog.md` — what we owe. Add the entry when you defer, not at the end.
- `doc/source/` — dated, immutable raw record (whiteboard photo, product brief, v0.1 intake).
  `fit-happens-intake-v2.md` is the merged intake. On conflict, the brief and v2 win.

## Hard rules — these are the product, not style preferences
1. **Slop Bouncer never rejects.** The verdict enum is `clear | inconclusive | flag_for_human`.
   There is no reject variant. Do not add one.
2. **Slop signals never reach the fit score.** `FitEngine` input types carry no style fields.
   Guarded by `test_fit_score_ignores_slop`.
3. **Style alone is never evidence.** Max style score + zero authenticity flags => `inconclusive`.
4. **Fabrication needs two independent flags** — distinct `pattern_id` AND distinct span.
5. **Absence of evidence is never evidence of absence.** Two places this bites, same rule:
   - No public GitHub must not cost a candidate a single point.
   - A hard gate the resume is *silent* on (work authorisation, clearance) must not cap the
     score. Only a *contradicted* gate caps. Silence becomes a follow-up question, not a
     penalty - see `Match.basis`. Guarded by `test_unstated_dealbreaker_does_not_cap_the_score`
     and `test_silence_never_scores_worse_than_contradiction`.
6. **Decisions come from the pure-Python rules engine, never the LLM.** The LLM extracts and
   drafts; it does not decide. Date arithmetic is always deterministic.
7. **Every score component carries an evidence span.** No span, no score.
8. **Consent gates the fetch, not the display.** Nothing external is retrieved before the
   candidate grants that scope, and withdrawing deletes what was gathered under it. Every
   offered scope must be read by `pipeline.n_verify` - a toggle nothing reads is worse than no
   toggle. Guarded by `test_every_consent_scope_actually_changes_behaviour`.
9. **CP1 style does not discriminate, and we say so.** Measured on 60 real resumes vs LLM
   rewrites of the same resumes: 0% detection at 0% false positives. It stays advisory and is
   structurally barred from contributing to a flag.

## Surfaces
**Two audiences, two doors.** `/` is a split landing - candidate or employer. It used to be the
recruiter dashboard, so an applicant landed on other applicants' names and fit scores.

Candidate (public): `/` · `/jobs` board · `/jobs/{slug}` advert + our clarity read ·
`/jobs/{slug}/apply` · `/apply/{token}` their application · `/track` recover a lost link.
Private preferences are never rendered on a candidate-facing page.

Recruiter (behind `FIT_HAPPENS_TEAM_PASSCODE`, read from the shell or a `.env`; open with a
visible banner if unset): `/hiring` overview · `/hiring/roles` list · `/hiring/roles/new` →
`/hiring/roles/preview` → create · `/hiring/role/{slug}/edit` · close/reopen ·
`/hiring/role/{slug}` ranking · `/hiring/role/{slug}/compare?ids=a,b` ·
`/hiring/role/{slug}/c/{cid}` evidence · `.../ask` · `/hiring/market`. Stages live in `stages.py` and are ALWAYS set by a person - that module must never
read a score, pinned by an AST test.
Candidate: `/apply/{token}` - status, consent, what-we-read, what-we-noticed, questions.
Tokens come from `ConsentStore(slug).token_for(candidate_id)`; every store is per-role.

**Run the demo WITHOUT `--reload`.** The reloader restarts the process on any file change and
kills in-flight upload tasks; the state file survives, so the page would spin on work that is
never coming back. `tasks.pending()` reaps anything past 480s, but the upload is still lost.
A CV takes 1-3 minutes cold (measured 153s for a long one) and seconds once cached.

## Stack
Python 3.12 + `uv` (never `python -m venv`). FastAPI + Jinja2 + Tailwind CDN.
LangGraph orchestration; `ChatOpenAI` from `langchain_openai`, structured output via
`.with_structured_output()`. Routing lives in `config/models.yaml`, never inline.

**Primary: DeepSeek V4 Flash via OpenRouter. Fallback: NVIDIA NIM, automatic on any error.**
Measured on one resume chunk: DeepSeek 59 claims/14.4s, NIM 33 claims/31.7s.

Both are REASONING models and each disables it differently - OpenRouter wants
`reasoning.enabled=false`, NIM wants `chat_template_kwargs.thinking=false`. Getting this wrong
is not a slow path but a broken one: with reasoning on and a small `max_tokens`, DeepSeek
returns `content: null` at HTTP 200 having spent the whole budget on the trace.

## Env vars (names only — never read or echo values)
`OPENROUTER_API_KEY` (primary) · `NVIDIA_API_KEY` (fallback) · `GITHUB_TOKEN` (optional;
60 req/h without it) · `FIT_HAPPENS_OFFLINE=1` for cache-only replay

## Gotchas that will bite you
- **NIM has no `/v1/completions`** (404) — only `/v1/chat/completions` and `/v1/embeddings`.
  Anything needing logprobs from the legacy completions API is off the table.
- **`/v1/models` is public** — a 200 there does not prove your key works. Test a chat call.
- **NIM free tier is ~40 req/min.** Bulk work goes through the disk cache; never live.
- **Off-page text: engines disagree, and that disagreement IS the detector.** Verified on a
  reportlab fixture whose injected text is physically in the content stream: `pdfplumber` and
  `pdfminer` extract it; `pymupdf` and `pypdfium2` do not. Clearing
  `TEXT_MEDIABOX_CLIP` changes nothing — that lever does not exist. Do not "fix" PyMuPDF;
  run two engines and flag the delta (`ingest/divergence.py`).
- **PyMuPDF is AGPL.** Fine for the hackathon; blocks permissive open-sourcing. `pypdfium2`
  (Apache/BSD) exposes render mode, fill colour and font size if we need to swap.
- **AI-text detectors are unsafe per-bullet.** Score the whole résumé (400-700 words) or not at
  all. See the engineering log for the citations.
