"""Near-identical job postings: the candidate's "blind discovery" problem.

The challenge's fourth candidate pain is *"the right role is hidden in a sea of near-identical
postings"*. I wrote this off as unbuildable - a near-duplicate detector over one job advert is
theatre - and that was right until we had a corpus. We now have a snapshot of real postings
(`data/postings/snapshot.json`, JobDataLake), and the pain turns out to be worse than the slide
suggests.

In one 30-day pull for "platform engineer", a single employer had **47 postings that are the
same job**: identical title, identical skill list, differing only by city. A candidate scrolling
a job board sees 47 results and cannot tell they are one opening. Clustering them is not a
trick - it is the whole of the problem, stated plainly.

The salary spread inside a cluster turns out to be the more useful output. The same role at the
same company is advertised at $140-200k in US cities and $30-120k in European ones. A candidate
comparing two postings has no way to see that; a candidate shown the cluster does.

Deterministic: title normalisation plus skill-set overlap. No model call, no embedding service,
and the reasoning is inspectable by the person it affects.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DATA_DIR

SNAPSHOT = DATA_DIR / "postings" / "snapshot.json"

# Words that vary between postings of the same job without changing what the job is.
NOISE = re.compile(
    r"\b(senior|snr|sr|junior|jnr|jr|lead|principal|staff|associate|mid|level|i{1,3}|iv|v|"
    r"remote|hybrid|onsite|on-site|contract|permanent|full|part|time|m|f|d|w|x|"
    r"emea|apac|us|usa|uk|eu|germany|france|india)\b", re.I)
PUNCT = re.compile(r"[^a-z0-9 ]")


def normalise_title(title: str) -> str:
    t = PUNCT.sub(" ", title.lower())
    t = NOISE.sub(" ", t)
    return " ".join(t.split())


def skill_overlap(a: list[str], b: list[str]) -> float:
    sa = {s.lower() for s in a}
    sb = {s.lower() for s in b}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass
class Cluster:
    title: str
    company: str
    postings: list[dict] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.postings)

    @property
    def locations(self) -> list[str]:
        return sorted({p["location"] for p in self.postings})

    @property
    def salary_range(self) -> tuple[int, int] | None:
        lows = [p["salary_min"] for p in self.postings if p.get("salary_min")]
        highs = [p["salary_max"] for p in self.postings if p.get("salary_max")]
        return (min(lows), max(highs)) if lows and highs else None

    @property
    def undisclosed(self) -> int:
        return sum(1 for p in self.postings if not p.get("salary_min"))

    @property
    def pay_varies_by_location(self) -> bool:
        """The finding worth surfacing: the same job priced differently by city."""
        lows = [p["salary_min"] for p in self.postings if p.get("salary_min")]
        return len(lows) > 1 and max(lows) >= 2 * min(lows)

    def summary(self) -> str:
        bits = [f"{self.size} postings of what looks like one job at {self.company}"]
        if len(self.locations) > 1:
            bits.append(f"across {len(self.locations)} locations")
        if r := self.salary_range:
            bits.append(f"advertised anywhere from ${r[0]}k to ${r[1]}k")
        if self.undisclosed:
            bits.append(f"{self.undisclosed} not stating pay at all")
        return ", ".join(bits)


def load_snapshot(path: Path = SNAPSHOT) -> dict:
    return json.loads(path.read_text()) if path.exists() else {"jobs": []}


def cluster_postings(jobs: list[dict], min_overlap: float = 0.6) -> list[Cluster]:
    """Group postings that are the same job. Same company, same normalised title, and
    substantially the same skills - all three, because two genuinely different roles at one
    company often share a title stem."""
    clusters: list[Cluster] = []
    for jb in jobs:
        key = normalise_title(jb["title"])
        for c in clusters:
            if c.company != jb["company"] or normalise_title(c.title) != key:
                continue
            if skill_overlap(c.postings[0].get("skills", []), jb.get("skills", [])) >= min_overlap:
                c.postings.append(jb)
                break
        else:
            clusters.append(Cluster(title=jb["title"], company=jb["company"], postings=[jb]))
    return sorted(clusters, key=lambda c: -c.size)


def duplicates(min_size: int = 2, path: Path = SNAPSHOT) -> list[Cluster]:
    return [c for c in cluster_postings(load_snapshot(path).get("jobs", [])) if c.size >= min_size]


def corpus_stats(path: Path = SNAPSHOT) -> dict:
    snap = load_snapshot(path)
    jobs = snap.get("jobs", [])
    clusters = cluster_postings(jobs)
    dupes = [c for c in clusters if c.size >= 2]
    hidden = sum(c.size - 1 for c in dupes)
    return {
        "source": snap.get("source", ""), "pulled": snap.get("pulled", ""),
        # a missing snapshot returns {"jobs": []}, with no total_matching - and None then
        # reaches "{:,}".format in the template and 500s the whole market page.
        "total_matching": snap.get("total_matching") or 0, "postings": len(jobs),
        "distinct_jobs": len(clusters), "duplicate_families": len(dupes),
        "redundant_postings": hidden,
        "redundancy": round(hidden / len(jobs), 3) if jobs else 0.0,
        "largest": dupes[0] if dupes else None,
    }
