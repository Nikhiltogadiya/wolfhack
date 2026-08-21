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


class TestStuckUploads:
    """uvicorn --reload kills in-flight background tasks. The state file survives, so without
    this the page spins forever on work that will never finish."""

    def test_a_task_running_too_long_is_reported_as_failed(self, tmp_path, monkeypatch):
        from datetime import datetime, timedelta, timezone

        from fit_happens.web import tasks
        monkeypatch.setattr(tasks, "DATA_DIR", tmp_path)
        tid = tasks.start("r", "cv.pdf")
        tasks.update("r", tid, "running", "extracting")

        old = (datetime.now(timezone.utc) - timedelta(seconds=tasks.STALE_AFTER_SECONDS + 60))
        d = tasks._read("r")
        d["items"][0]["at"] = old.isoformat(timespec="seconds")
        tasks._write("r", d)

        assert tasks.pending("r") == []
        assert "restarted" in tasks.failed("r")[0]["error"]

    def test_a_recent_task_is_left_alone(self, tmp_path, monkeypatch):
        from fit_happens.web import tasks
        monkeypatch.setattr(tasks, "DATA_DIR", tmp_path)
        tid = tasks.start("r", "cv.pdf")
        tasks.update("r", tid, "running", "extracting")
        assert len(tasks.pending("r")) == 1

    def test_the_cutoff_is_above_a_real_cold_run(self):
        """Measured: a long CV takes ~150s. A cutoff near that would reap live work."""
        from fit_happens.web import tasks
        assert tasks.STALE_AFTER_SECONDS > 300


def test_looking_up_a_role_does_not_create_it(tmp_path, monkeypatch):
    """Constructing a Run used to mkdir, so visiting /role/typo brought an empty role into
    existence. A crawler or a mistyped URL would fill the data directory with them."""
    import fit_happens.store as store
    monkeypatch.setattr(store, "RUNS", tmp_path / "runs")
    run = store.Run("a-role-that-does-not-exist")
    assert not run.exists
    assert not run.dir.exists(), "merely looking up a role created it"
    assert store.roles() == []


class TestStages:
    """A tool that can only record a 'no' quietly frames every decision as one."""

    def test_a_new_candidate_starts_at_new(self, tmp_path, monkeypatch):
        import fit_happens.stages as st
        monkeypatch.setattr(st, "DATA_DIR", tmp_path)
        assert st.StageStore().load("x").stage == "new"

    def test_moving_stage_records_who_and_when(self, tmp_path, monkeypatch):
        import fit_happens.stages as st
        monkeypatch.setattr(st, "DATA_DIR", tmp_path)
        s = st.StageStore()
        s.set("x", "reviewing")
        rec = s.set("x", "shortlisted")
        assert rec.stage == "shortlisted"
        assert [h["to"] for h in rec.history] == ["reviewing", "shortlisted"]
        assert all(h["actor"] == "recruiter" for h in rec.history)

    def test_setting_the_same_stage_twice_adds_no_history(self, tmp_path, monkeypatch):
        import fit_happens.stages as st
        monkeypatch.setattr(st, "DATA_DIR", tmp_path)
        s = st.StageStore()
        s.set("x", "reviewing")
        assert len(s.set("x", "reviewing").history) == 1

    def test_an_unknown_stage_is_refused(self, tmp_path, monkeypatch):
        import fit_happens.stages as st
        monkeypatch.setattr(st, "DATA_DIR", tmp_path)
        assert st.StageStore().set("x", "hired_immediately").stage == "new"

    def test_the_system_never_sets_a_stage_from_a_score(self):
        """Stages are a human decision. If this module ever reads a score it has become an
        automated hiring decision, which is the one thing we promise not to make.

        Checked against the parsed AST, not the source text: an earlier version grepped the
        raw file and failed on the word "flags" in this module's own docstring, which proves
        nothing about the code.
        """
        import ast
        import inspect

        import fit_happens.stages as st

        tree = ast.parse(inspect.getsource(st))
        imported = {
            n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        } | {
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
        }
        assert not any("schemas" in m or "fit" in m.split(".") for m in imported), imported

        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for banned in ("score", "verdict", "flags", "cp2", "fit"):
            assert banned not in attrs, f"stages reads .{banned}"


def test_one_stalled_chunk_is_retried_not_fatal(monkeypatch):
    """A hung call used to fail the whole CV, wasting the other chunks' work and showing an
    error for a document that reads perfectly well."""
    from fit_happens.fit import extract_claims as ex

    calls = {"n": 0}

    def fake_many(task, schema, prompts, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return [schema(claims=[], employment=[]), None, schema(claims=[], employment=[])]
        return [schema(claims=[], employment=[])]  # the retry succeeds

    monkeypatch.setattr(ex.llm, "structured_many", fake_many)
    monkeypatch.setattr(ex, "chunk_text", lambda t, size=0: ["a", "b", "c"])

    class Doc:
        text = "a\nb\nc"

    claims, employment = ex.extract_claims(Doc())
    assert calls["n"] == 2, "the failed chunk was not retried"
    assert claims == [] and employment == []


def test_a_chunk_that_fails_twice_fails_loudly(monkeypatch):
    """Silently dropping it would lose claims without saying so."""
    import pytest as _pytest

    from fit_happens.fit import extract_claims as ex

    monkeypatch.setattr(ex.llm, "structured_many", lambda t, s, p, **k: [None] * len(p))
    monkeypatch.setattr(ex, "chunk_text", lambda t, size=0: ["a", "b"])

    class Doc:
        text = "a\nb"

    with _pytest.raises(RuntimeError, match="could not be read"):
        ex.extract_claims(Doc())
