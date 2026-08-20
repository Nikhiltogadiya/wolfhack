"""Run the Fit Engine end to end on one or more resumes against one JD."""

from __future__ import annotations

import argparse
import glob
import sys
import warnings

warnings.simplefilter("ignore")

from fit_happens.fit import extract_claims, map as mapper, score as scorer
from fit_happens.ingest import forensics
from fit_happens.jd import parse as jdparse


def find_pdf(resume_id: str) -> str:
    hits = glob.glob(f"data/corpus/data/data/*/{resume_id}.pdf")
    if not hits:
        sys.exit(f"no PDF for id {resume_id}")
    return hits[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jd", default="data/demo/jd_external.md")
    ap.add_argument("ids", nargs="+")
    args = ap.parse_args()

    title, reqs = jdparse.parse_jd(open(args.jd).read())
    n_req = sum(1 for r in reqs if r.kind == "required")
    n_pref = len(reqs) - n_req
    n_deal = sum(1 for r in reqs if r.dealbreaker)
    print(f"JD: {title}")
    print(f"    {len(reqs)} requirements  ({n_req} required, {n_pref} preferred, {n_deal} dealbreakers)\n")

    results = []
    for rid in args.ids:
        path = find_pdf(rid)
        category = path.split("/")[-2]
        doc = forensics.ingest(path)
        claims, employment = extract_claims.extract_claims(doc)
        matches = mapper.map_claims(claims, reqs, employment)
        fit = scorer.score_fit(matches, reqs)
        results.append((rid, category, doc, claims, employment, fit))

    results.sort(key=lambda r: -r[5].score)
    print(f"{'rank':<5}{'candidate':<12}{'category':<24}{'fit':>7}{'req':>7}{'pref':>7}  gaps")
    print("-" * 78)
    for i, (rid, cat, doc, claims, emp, fit) in enumerate(results, 1):
        crit = sum(1 for g in fit.gaps if g.severity == "critical")
        maj = sum(1 for g in fit.gaps if g.severity == "major")
        print(f"{i:<5}{rid:<12}{cat[:22]:<24}{fit.score:>6.0%}{fit.required_coverage:>7.0%}"
              f"{fit.preferred_coverage:>7.0%}  {crit} critical, {maj} major")

    print()
    for rid, cat, doc, claims, emp, fit in results:
        print(f"--- {rid} ({cat}) — {len(claims)} claims, {len(emp)} roles, "
              f"{len(doc.text)} chars, hidden={len(doc.hidden)}")
        strong = [m for m in fit.matches if m.strength == "strong"]
        for m in strong[:3]:
            req = next(r for r in reqs if r.id == m.requirement_id)
            print(f"      STRONG  {req.text[:58]:60} <- {m.rationale[:70]}")
        for g in [g for g in fit.gaps if g.severity in ("critical", "major")][:3]:
            print(f"      {g.severity.upper():8} {g.text[:58]}")
        print()


if __name__ == "__main__":
    main()
