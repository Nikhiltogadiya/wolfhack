"""Build the demo run: parse the JD, score every demo candidate, store the results."""

from __future__ import annotations

import argparse
import glob
import sys
import time
import warnings

warnings.simplefilter("ignore")

from fit_happens.jd import parse as jdparse
from fit_happens.jd.model import InternalConstraint, JobDescription
from fit_happens.jd.slop import scan_job_ad
from fit_happens.pipeline import run_candidate
from fit_happens.store import Run

# Real operational constraints plus one that must be refused - the guard is part of the demo,
# so the refusal has to be visible in the audit trail rather than described in a slide.
#
# The first one is the interesting one, and it is the reason the internal JD exists at all.
# A company does not publish "we are going into an ISO 27001 audit next year" in a job advert -
# it signals that your controls are not in order. But it is exactly the kind of unpublishable
# operational fact that changes who the right hire is, and it is a legitimate requirement about
# the work rather than about the person.
INTERNAL = [
    InternalConstraint(
        field_name="team_context",
        value=("we go into an ISO 27001 audit next year, so this hire must have worked under a "
               "formal compliance or accreditation regime"),
        required=True, weight=1.5),
    InternalConstraint(field_name="mentoring_capacity", value="the team is junior, this hire must mentor two engineers", required=True),
    InternalConstraint(field_name="onsite_days", value="three days a week in the Berlin office"),
    # Must be refused. Kept in the demo on purpose: the guard is only credible if you watch it
    # reject something.
    InternalConstraint(field_name="team_context", value="we want a young energetic team with no career gaps"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jd", default="data/demo/jd_external.md")
    ap.add_argument("ids", nargs="+")
    args = ap.parse_args()

    text = open(args.jd).read()
    title, external = jdparse.parse_jd(text)
    jd = JobDescription(title=title, external_text=text, internal=INTERNAL)
    requirements = external + jd.internal_requirements()
    _, ad_flags, clarity = scan_job_ad(text)

    run = Run()
    run.save_role(jd, requirements, clarity, ad_flags)
    print(f"role: {title}")
    print(f"  {len(external)} external + {len(requirements) - len(external)} internal requirements"
          f"  |  {jd.blocked_count()} internal criteria REFUSED  |  ad clarity {clarity:.0%}\n")

    for rid in args.ids:
        hits = glob.glob(f"data/corpus/data/data/*/{rid}.pdf") or glob.glob(rid)
        if not hits:
            print(f"  ! no file for {rid}")
            continue
        t0 = time.time()
        result = run_candidate(hits[0], jd, requirements)
        run.save_candidate(result)
        print(f"  {rid:14} fit={result.fit.score:5.0%}  style={result.style_label:6} "
              f"bluff={result.bluff_label:14} claims={len(result.claims):3} "
              f"hidden={len(result.document.hidden)}  {time.time()-t0:5.1f}s")


if __name__ == "__main__":
    main()
