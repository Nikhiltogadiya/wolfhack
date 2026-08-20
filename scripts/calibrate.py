"""Measure what checkpoint 1 actually does, on labelled data.

Intake §11 question 5 asks what ground truth exists for "this CV is bluffing". The honest
answer was: none. This builds some.

* **Known human** - real resumes from a public corpus, scraped from a resume-builder site and
  predating the LLM era.
* **Known AI** - the *same* resumes, rewritten by a model with the prompt a job applicant would
  actually use. Same people, same facts, same distribution: the only variable is who wrote the
  prose. That is what makes a false-positive rate mean something.

The rewrite prompt deliberately asks for a normal polish job, not a caricature. Measuring
against slop we wrote ourselves would only prove we can detect our own writing.

Reported at the end: false-positive rate on real humans, true-positive rate on rewrites, and
the spread of false positives ACROSS JOB CATEGORIES - a fairness check that needs no inference
about any protected characteristic, which is the point.
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
import warnings
from collections import defaultdict

warnings.simplefilter("ignore")
csv.field_size_limit(10**7)

from pydantic import BaseModel, Field

from fit_happens import config, llm
from fit_happens.slop.style import read_style


class _Rewrite(BaseModel):
    resume: str = Field(description="the rewritten resume, full text")


REWRITE_PROMPT = """Rewrite this resume so it reads more polished and professional, the way a
job applicant would ask an AI assistant to tidy it up before applying.

Keep every fact, employer, date and number exactly as they are. Do not invent anything. Improve
the phrasing, make the bullets read well, and keep it the same length. Keep it laid out as a
resume with one bullet or heading per line.

{resume}"""


def load_corpus(n: int, seed: int) -> list[tuple[str, str, str]]:
    """Load from the PDFs, not the CSV.

    The CSV column is a single flattened string with no line breaks. Reading it that way
    silently disables both bullet-rhythm patterns - `_bullets()` splits on newlines and gets
    nothing - so an earlier version of this script measured a detector with two of its
    strongest signals switched off, and reported the result as if it meant something.
    """
    import glob

    from fit_happens.ingest import extract

    paths = sorted(glob.glob("data/corpus/data/data/*/*.pdf"))
    random.Random(seed).shuffle(paths)
    out: list[tuple[str, str, str]] = []
    for path in paths:
        if len(out) >= n:
            break
        text = extract.primary_text(extract.extract_all(path))
        if len(text.split()) >= config.MIN_WORDS_FOR_STYLE_SCORE and "\n" in text:
            out.append((path.split("/")[-1][:-4], path.split("/")[-2], text))
    return out


def rate(scores: list[float], threshold: float) -> float:
    return sum(1 for s in scores if s >= threshold) / len(scores) if scores else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    corpus = load_corpus(args.n, args.seed)
    print(f"calibrating on {len(corpus)} real resumes + {len(corpus)} LLM rewrites of the same\n")

    human_scores, ai_scores = [], []
    by_category: dict[str, list[float]] = defaultdict(list)
    band_counts: dict[str, int] = defaultdict(int)

    # Line breaks must survive into the rewrite too, or the same two patterns are disabled on
    # the AI class only - which would understate detection rather than measure it.
    prompts = [REWRITE_PROMPT.format(resume=text[:6000]) for _, _, text in corpus]
    # Corpus items are independent, so a stuck or refused rewrite should shrink the sample
    # rather than stall the run. Pairs that fail are dropped from BOTH classes below, so the
    # two classes stay matched.
    rewrites = llm.structured_many("corpus_rewrite", _Rewrite, prompts, workers=6,
                                   timeout=120.0, tolerate_failures=True)
    dropped = sum(1 for r in rewrites if r is None)
    if dropped:
        print(f"  ({dropped} rewrites failed or timed out; those pairs are excluded)\n")

    for (rid, category, text), rw in zip(corpus, rewrites):
        if rw is None:
            continue
        h = read_style(text)
        human_scores.append(h.score)
        by_category[category].append(h.score)
        band_counts[h.band] += 1
        ai_scores.append(read_style(rw.resume).score)

    lo, hi = config.STYLE_GREY_BAND
    print(f"{'threshold':>10}  {'FPR (humans flagged)':>22}  {'TPR (rewrites caught)':>22}")
    print("-" * 60)
    for t in (0.25, lo, 0.5, hi, 0.85):
        marker = "  <- grey band" if t in (lo, hi) else ""
        print(f"{t:>10.2f}  {rate(human_scores, t):>21.1%}  {rate(ai_scores, t):>21.1%}{marker}")

    print(f"\nhuman   mean {statistics.mean(human_scores):.3f}  median {statistics.median(human_scores):.3f}")
    print(f"rewrite mean {statistics.mean(ai_scores):.3f}  median {statistics.median(ai_scores):.3f}")
    print(f"\nbands assigned to real humans: "
          + ", ".join(f"{k}={v} ({v/len(corpus):.0%})" for k, v in sorted(band_counts.items())))

    print("\nfalse-positive rate by job category, at the top of the grey band")
    print("(a fairness check that requires inferring nothing about any person)")
    rows = [(c, rate(s, hi), len(s)) for c, s in by_category.items() if len(s) >= 3]
    for c, r, n in sorted(rows, key=lambda x: -x[1])[:10]:
        print(f"   {c[:26]:28} {r:6.0%}   (n={n})")
    if len(rows) >= 3:
        spread = max(r for _, r, _ in rows) - min(r for _, r, _ in rows)
        print(f"\n   spread across categories: {spread:.0%}")

    sep = statistics.mean(ai_scores) - statistics.mean(human_scores)
    print(f"\nseparation between the two classes: {sep:+.3f}")
    if sep < 0.15:
        print("  -> WEAK. Report this honestly: the detector barely distinguishes an LLM polish")
        print("     of a real resume from the original. That is a finding, not a failure to hide.")


if __name__ == "__main__":
    main()
