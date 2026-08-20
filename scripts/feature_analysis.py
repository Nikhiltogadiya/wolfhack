"""Which style signals actually separate a real resume from an LLM polish of the same resume?

Written because the tuned detector scored 0% detection at 0% false positives on 60 real pairs.
The thresholds had been set against a caricature written by hand, not against what the system
actually meets. This measures the raw features on both classes so thresholds come from data.

Free to run: the features are deterministic and the rewrites are already cached.
"""

from __future__ import annotations

import re
import statistics
import sys
import warnings

warnings.simplefilter("ignore")

from fit_happens import llm
from fit_happens.slop import style as st

sys.path.insert(0, "scripts")
import calibrate as cal


def features(text: str) -> dict[str, float]:
    low = text.lower()
    bullets = st._bullets(text)
    lengths = [len(b.split()) for b in bullets] or [1]
    mean_len = statistics.mean(lengths)
    words = max(len(text.split()), 1)
    return {
        "stock_phrase_types": sum(1 for p in st.STOCK_PHRASES if re.search(rf"\b{re.escape(p)}\b", low)),
        "stock_per_100w": 100 * sum(low.count(p) for p in st.STOCK_PHRASES) / words,
        "self_significance": len(st.SELF_SIGNIFICANCE.findall(text)),
        "not_just_x": len(st.NOT_JUST_X_BUT_Y.findall(text)),
        "copula": len(st.COPULA_AVOIDANCE.findall(text)),
        "rule_of_three_frac": sum(1 for b in bullets if st.RULE_OF_THREE.search(b)) / max(len(bullets), 1),
        "em_dashes": len(st.EM_DASH.findall(text)),
        "bullet_cv": (statistics.pstdev(lengths) / mean_len) if mean_len else 1.0,
        "mean_bullet_len": mean_len,
    }


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    corpus = cal.load_corpus(n, 7)
    prompts = [cal.REWRITE_PROMPT.format(resume=t[:6000]) for _, _, t in corpus]
    rewrites = llm.structured_many("corpus_rewrite", cal._Rewrite, prompts, workers=6,
                                   timeout=120.0, tolerate_failures=True)

    pairs = [(t, r.resume) for (_, _, t), r in zip(corpus, rewrites) if r is not None]
    print(f"{len(pairs)} matched pairs\n")
    if not pairs:
        return

    keys = list(features(pairs[0][0]))
    h_feats = [features(h) for h, _ in pairs]
    a_feats = [features(a) for _, a in pairs]

    print(f"{'feature':22} {'human med':>10} {'AI med':>10} {'human p90':>10} "
          f"{'AI p90':>10} {'sep':>7}")
    print("-" * 74)
    rows = []
    for k in keys:
        hv = sorted(f[k] for f in h_feats)
        av = sorted(f[k] for f in a_feats)
        hp = hv[int(0.9 * (len(hv) - 1))]
        # Share of AI rewrites above the HUMAN 90th percentile. A threshold there costs about
        # 10% false positives by construction, so this is the detection you would buy for it.
        above = sum(1 for f in a_feats if f[k] > hp) / len(a_feats)
        rows.append((above, k, statistics.median(hv), statistics.median(av), hp,
                     av[int(0.9 * (len(av) - 1))]))
    for above, k, hm, am, hp, ap in sorted(rows, reverse=True):
        print(f"{k:22} {hm:10.2f} {am:10.2f} {hp:10.2f} {ap:10.2f} {above:6.0%}")

    print("\nsep = share of AI rewrites exceeding the HUMAN 90th percentile.")
    print("Under ~20% is noise: you would flag one in ten real people to catch fewer than")
    print("one in five rewrites.")


if __name__ == "__main__":
    main()
