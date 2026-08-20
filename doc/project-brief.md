# Fit Happens — project brief

Canonical spec. Derived from `doc/source/` (dated, immutable) + `fit-happens-intake-v2.md`.
This document is living and wins on conflict with the source record.

## The challenge (Akkodis)

*"The Talent Market Is Broken. AI Is Making It Worse."* Employers and candidates are both
drowning in AI-generated content while trustworthy information stays scarce. The ask: a
**trusted AI-powered Talent & Opportunity Marketplace** — from *static CVs + generic job ads*
to *dynamic signals + trusted AI insights*.

No judging-criteria slide exists, so the six **"Responsible AI by Design"** bullets are the
de-facto rubric. Each maps to an artefact, not a claim:

| Their bullet | Our artefact |
|---|---|
| Human in the loop | Verdict enum is `clear\|inconclusive\|flag_for_human`. `test_no_reject_path` |
| Transparent recommendations | Every score carries an evidence span; UI chips link to résumé line numbers |
| No automated hiring decisions | Same enum + persistent UI footer |
| Bias & fairness monitoring | Measured false-positive rate incl. non-native-English slice; protected-characteristic guard |
| GDPR-compliant processing | Exportable audit trail; PII confined to the candidate record |
| **User-controlled sharing** | **NOT BUILT.** Named as a known gap in the pitch (backlog #8) |

## The two components

**Fit Engine** ranks on *background*, not prose. `0.70 × required_coverage + 0.30 ×
preferred_coverage`, fixed. Dealbreakers raise a flag and cap fit at 49%. Gaps classified
critical/major/minor, seeding follow-up questions.

**Slop Bouncer** flags, never rejects. Three checkpoints (CP3 stubbed for the hackathon):
CP1 style on the raw résumé · CP2 claim consistency on mapped claims · CP3 response scan.

**GitHub verification** resolves each claim to `corroborated` / `unsupported` / **`undersold`**
(real evidence the CV never mentions). Undersold is the beat we lead with — the same mechanism
helping rather than policing. Absence of GitHub is *never* negative.

**JD slop scan** points CP1 at the employer's own job ad — Akkodis's candidate pain #1.

## Bluff patterns (8)

Six deterministic, two LLM. Deterministic: overlapping employment dates · expertise predating
the candidate's career *or the technology's release* · duplicate bullets across roles · round-
number density · certification-name registry · **JD echo** (n-gram overlap with the job ad —
recovered from the whiteboard's "CVs overfit on JD", which the intake doc had softened away).
LLM: unexplained expert-level skill · results implausible for company size.

## What the research changed

**AI-text detection is unsafe on résumés unless designed around.** Three independent sources:

- Liang et al., *Patterns* 2023 — 7 detectors on TOEFL essays: **61.22% average false-positive
  rate** for non-native writers vs near-zero for native. Mechanism is low perplexity, not deceit.
- Fraser, Dawkins & Kiritchenko (JAIR) — detectors *"require on the order of at least 100
  words"*; ~200 for reliability. **A résumé bullet is 10-25 words, so per-bullet detection is
  statistically meaningless.**
- NBER w34223 (Jabarian & Imas) — the RoBERTa baseline flags **30-69% of human text** and names
  résumé screening as unsuitable.

Design consequences, all now enforced: score the **whole résumé as one document**, never per
bullet; ship it as *"AI-assisted writing likelihood"*, a spectrum with a wide grey band, never a
verdict; and surface the non-native-English caveat **in the UI**, not the docs. This is the
evidence behind house rule 3 — we can cite it on stage.

**Prompt-injection guards over-defend.** The InjecGuard/PIGuard paper shows guard models drop to
~60% accuracy on benign text containing trigger words. A résumé that legitimately says "prompt
injection" or "jailbreak" — i.e. an LLM security engineer — gets flagged. Use PIGuard (MIT),
which specifically fixes this, over the archived ProtectAI stack.

## Milestones

| # | Milestone | Gate |
|---|---|---|
| M0 | Toolchain spine | Real NIM call returns validated Pydantic; identical call cache-served offline |
| M1 | Ingest + forensics | Poisoned PDF caught, span quoted with provenance, **never reaches the prompt** |
| M2 | JD model + protected-characteristic guard | Blocked field provably absent from scoring input |
| M3 | Fit Engine | Right-background/flat outranks wrong-background/polished; separation invariant holds |
| M4 | Slop CP1 + CP2, 8 patterns | ≥2 independent flags before "likely fabricated"; style-only → inconclusive |
| M5 | GitHub verification | `test_missing_github_never_lowers_any_score`; undersold renders |
| M6 | JD slop scan *(first cut)* | Generic JD scores visibly worse than a specific one |
| M7 | Follow-up questions | Template fallback works with the LLM disabled |
| M8 | Dashboard, 3 screens | Internal-JD toggle visibly re-orders the ranking |
| M9 | Demo corpus + pre-warm | Whole demo runs with the network cable out |
| M10 | Calibration *(second cut)* | A real false-positive number for the stage |
| M11 | Rehearsal + docs | Script runs start to finish twice, offline |

Honest estimate: ~26h of work in 24. Cut order is fixed above so it is decided now, not at
hour 20.

## Demo

Three candidates from the real corpus, reproducing intake §7 — two of the three are **real human
résumés**, not hand-crafted:

- **A** right background, real, plainly written → high fit, low sloppiness, no flags
- **B** wrong background, real, well written, untouched → low fit, low sloppiness, **no flags**
  (nothing is fabricated; the background is simply wrong). *Only the fit column catches B.*
- **C** real résumé, LLM-rewritten with known injected defects → mid fit, high sloppiness, ≥2
  corroborated flags. Defects known by construction, so it doubles as a labelled test case.

Beats: ① A vs B side by side ② internal-JD reveal → guard rejects a protected characteristic →
exported audit trail ③ GitHub **undersold** ④ the injection catch.

**Do not quote 95/95/71/59/14.** That evidence belongs to a test set that does not exist on this
machine and cannot be reproduced; presenting it as our result would claim a number we never
measured. Quote M10's numbers instead.
