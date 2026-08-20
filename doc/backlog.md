# Backlog

What we still owe. One line per item, added **at the moment of deferral**.
Status: `DEFERRED` (do later) · `UNVERIFIED` (claimed, not confirmed) · `BLOCKED` (waiting on
someone) · `WONTFIX` (decided against, reason recorded) · `DONE` (with date).

| # | Status | Item | Why | Where it would go | Trigger to pick up |
|---|---|---|---|---|---|
| 1 | BLOCKED | Kaggle `snehaanbhawal/resume-dataset` download | No Kaggle credentials on this machine | `data/corpus/` | User downloads it |
| 2 | BLOCKED | `GITHUB_TOKEN` | Not set; 60 req/h unauthenticated vs 5,000 | env | User creates a fine-grained read-only token |
| 3 | DEFERRED | Checkpoint 3 — response scan | Needs a second candidate-facing UI; intake §10 says stub it | `slop/response.py` | Post-hackathon, or if M10 lands early |
| 4 | WONTFIX | Voice / on-demand questions | Expensive, adds little to a judged demo (intake §10). Web Speech API if a sponsor prize ever needs it | — | A sponsor prize requires it |
| 5 | WONTFIX | Industry skill matching | No definition distinct from the 70/30 mapping (intake §3 [OPEN]) | — | Someone defines what it does |
| 6 | WONTFIX | Cross-JD matching, SAP SuccessFactors, Δ/JD-authoring, closed-loop retraining | Explicitly killed in intake v0.1 §3 | — | Never — recorded so they don't creep back |
| 7 | DEFERRED | Recruiter rejection feedback | ~20 min (textarea + storage), no demo payoff | `web/` + store | If M10 finishes early |
| 8 | DEFERRED | User-controlled sharing (candidate consent UI) | The one Akkodis "Responsible AI" bullet we do not satisfy | new candidate-side surface | Post-hackathon. **Name it in the pitch as a known gap** |
| 9 | UNVERIFIED | NIM `top_logprobs` support | Docs silent; would enable perplexity-based detection | `slop/style.py` | Test `logprobs:true, top_logprobs:5` on a chat call |
| 10 | DEFERRED | Off-page text detection | The one gap in the vendored HCD detector; ~10 lines comparing span bbox to `page.rect` | `ingest/forensics.py` | M1 |
| 11 | UNVERIFIED | CPU latency of the AI-text and injection classifiers | No benchmark run; treat speed claims as unmeasured | — | First time the demo feels slow |
| 12 | DEFERRED | Swap PyMuPDF for pypdfium2 | PyMuPDF is AGPL; blocks permissive open-sourcing | `ingest/` | If this repo goes public |
| 13 | UNVERIFIED | "detectors need >=100 words" (Fraser et al. JAIR 82:2233-2278) | Could not retrieve paper text; NBER w34223 cuts against it (Pangram works on <50-word stubs). Not used as a design constraint | `doc/project-brief.md` | If someone gets the JAIR full text |
| 14 | WONTFIX | Neural AI-text classifier as a scored signal | Liang et al. measured 61.22% FPR for non-native writers; mechanism is low perplexity, so all perplexity-based detectors inherit it. Deterministic pattern scoring instead | `slop/style.py` | Only if a non-perplexity detector with published non-native FPR appears |
