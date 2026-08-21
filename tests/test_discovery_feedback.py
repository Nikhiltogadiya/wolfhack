"""Near-duplicate postings and recruiter feedback.

Both were written off earlier in the build - blind discovery as unbuildable without a corpus,
feedback as low value. The corpus arrived, and the feedback loop turns out to be the only
signal we have that does not require waiting to see who was hired.
"""

from __future__ import annotations

import pytest

from fit_happens.feedback import REASONS, FeedbackStore, Rejection
from fit_happens.jd.discovery import (
    Cluster, cluster_postings, corpus_stats, duplicates, normalise_title, skill_overlap,
)


def _p(company, title, loc, skills, lo=None, hi=None):
    return {"company": company, "title": title, "location": loc, "skills": skills,
            "salary_min": lo, "salary_max": hi, "remote": "hybrid", "id": f"{company}-{loc}"}


class TestTitleNormalisation:
    @pytest.mark.parametrize("a,b", [
        ("Senior Platform Engineer", "Platform Engineer"),
        ("Principal Platform Engineer", "Staff Platform Engineer"),
        ("Platform Engineer (Remote)", "Platform Engineer"),
        ("Platform Engineer (m/f/d)", "Platform Engineer"),
        ("Platform Engineer II", "Platform Engineer"),
    ])
    def test_level_and_location_noise_collapses(self, a, b):
        assert normalise_title(a) == normalise_title(b)

    @pytest.mark.parametrize("a,b", [
        ("Platform Engineer", "Data Engineer"),
        ("Frontend Engineer", "Backend Engineer"),
        ("Platform Engineer", "Engineering Manager"),
    ])
    def test_genuinely_different_roles_stay_different(self, a, b):
        assert normalise_title(a) != normalise_title(b)


def test_skill_overlap_is_jaccard():
    assert skill_overlap(["a", "b"], ["a", "b"]) == 1.0
    assert skill_overlap(["a", "b"], ["c", "d"]) == 0.0
    assert skill_overlap([], ["a"]) == 0.0


class TestClustering:
    def test_same_job_in_many_cities_is_one_cluster(self):
        sk = ["Node.js", "TypeScript", "AWS", "Kubernetes"]
        jobs = [_p("Speechify", "Software Engineer, Platform", c, sk)
                for c in ("Tokyo", "Paris", "Austin", "Milan")]
        clusters = cluster_postings(jobs)
        assert len(clusters) == 1 and clusters[0].size == 4

    def test_different_companies_never_merge(self):
        sk = ["Kubernetes", "Terraform"]
        clusters = cluster_postings([_p("A", "Platform Engineer", "X", sk),
                                     _p("B", "Platform Engineer", "X", sk)])
        assert len(clusters) == 2

    def test_same_title_but_different_skills_stays_separate(self):
        """Two genuinely different roles at one company often share a title stem."""
        clusters = cluster_postings([
            _p("A", "Platform Engineer", "X", ["Kubernetes", "Terraform", "AWS", "Go"]),
            _p("A", "Platform Engineer", "Y", ["Salesforce", "Excel", "SAP", "Workday"])])
        assert len(clusters) == 2

    def test_pay_varying_by_city_is_surfaced(self):
        sk = ["Node.js", "AWS"]
        c = cluster_postings([_p("S", "Engineer", "NY", sk, 140, 200),
                              _p("S", "Engineer", "Milan", sk, 30, 80)])[0]
        assert c.pay_varies_by_location
        assert c.salary_range == (30, 200)

    def test_similar_pay_is_not_flagged_as_varying(self):
        sk = ["Node.js", "AWS"]
        c = cluster_postings([_p("S", "Engineer", "NY", sk, 140, 200),
                              _p("S", "Engineer", "Boston", sk, 135, 195)])[0]
        assert not c.pay_varies_by_location


def test_the_real_snapshot_finds_real_duplication():
    """Pinned against the shipped snapshot so a data refresh that breaks clustering is loud."""
    s = corpus_stats()
    assert s["postings"] > 50
    assert s["distinct_jobs"] < s["postings"], "clustering did nothing"
    assert s["redundancy"] > 0.4, "expected heavy duplication in a real 30-day pull"
    biggest = duplicates()[0]
    assert biggest.size >= 20, "the headline cluster should be large"
    assert biggest.pay_varies_by_location


class TestRecruiterFeedback:
    def test_every_reason_names_what_it_would_change(self):
        """'Not a fit' tells us nothing. Each reason maps to a part of the system."""
        for key, meta in REASONS.items():
            assert meta["label"] and len(meta["signal"]) > 15, key

    def test_a_misread_cv_is_recorded_as_our_error(self):
        r = Rejection(candidate_id="x", reason="we_misread_the_cv", fit_score=0.7)
        assert r.is_our_error and r.contradicts_our_ranking

    def test_a_rejection_at_a_low_score_teaches_us_nothing(self):
        assert not Rejection(candidate_id="x", reason="wrong_seniority",
                             fit_score=0.04).contradicts_our_ranking

    def test_pipeline_reasons_are_excluded_from_the_signal(self):
        """'They already accepted elsewhere' says nothing about our scoring."""
        assert not Rejection(candidate_id="x", reason="already_progressed",
                             fit_score=0.9).contradicts_our_ranking

    def test_summary_counts_and_survives_a_round_trip(self, tmp_path, monkeypatch):
        import fit_happens.feedback as fb
        monkeypatch.setattr(fb, "DATA_DIR", tmp_path)
        store = fb.FeedbackStore()
        store.record(fb.Rejection(candidate_id="a", reason="we_misread_the_cv", fit_score=0.8))
        store.record(fb.Rejection(candidate_id="b", reason="wrong_seniority", fit_score=0.6))
        s = store.summary()
        assert s["total"] == 2 and s["our_errors"] == 1 and s["contradicting"] == 2
        assert store.get("a").is_our_error
