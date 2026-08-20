# Fit Happens — project memory

Akkodis hackathon build (~24h, solo). Ranks who **fits** a role; flags who **isn't real**.
Two components that must never contaminate each other: **Fit Engine** (matching) and
**Slop Bouncer** (detection).

## Read before touching anything
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
5. **Absence of external evidence is never a negative signal.** No public GitHub must not cost
   a candidate a single point. Guarded by `test_missing_github_never_lowers_any_score`.
6. **Decisions come from the pure-Python rules engine, never the LLM.** The LLM extracts and
   drafts; it does not decide. Date arithmetic is always deterministic.
7. **Every score component carries an evidence span.** No span, no score.

## Stack
Python 3.12 + `uv` (never `python -m venv`). FastAPI + Jinja2 + Tailwind CDN.
LangGraph orchestration; `ChatOpenAI` from `langchain_openai` pointed at NVIDIA NIM
(`https://integrate.api.nvidia.com/v1`), structured output via `.with_structured_output()`.
Default model `nvidia/nemotron-3-nano-30b-a3b`; see `config/models.yaml`.

## Env vars (names only — never read or echo values)
`NVIDIA_API_KEY` (required) · `GITHUB_TOKEN` (optional; 60 req/h without it)

## Gotchas that will bite you
- **NIM has no `/v1/completions`** (404) — only `/v1/chat/completions` and `/v1/embeddings`.
  Anything needing logprobs from the legacy completions API is off the table.
- **`/v1/models` is public** — a 200 there does not prove your key works. Test a chat call.
- **NIM free tier is ~40 req/min.** Bulk work goes through the disk cache; never live.
- **PyMuPDF `TEXT_MEDIABOX_CLIP` (64) is ON by default** and silently discards off-page text —
  one of the attacks we hunt. Clear it when extracting spans.
- **PyMuPDF is AGPL.** Fine for the hackathon; blocks permissive open-sourcing. `pypdfium2`
  (Apache/BSD) exposes render mode, fill colour and font size if we need to swap.
- **AI-text detectors are unsafe per-bullet.** Score the whole résumé (400-700 words) or not at
  all. See the engineering log for the citations.
