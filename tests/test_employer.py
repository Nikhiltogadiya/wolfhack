"""The employer side, from walking it signed in as a recruiter.

Every test here corresponds to something that was wrong when I used it: an applicant displayed
as "Naledi Dube 7B4F54", another as "15118506", no way to fix a typo in an advert, no way to
close a filled role, no way to remove a duplicate, and five page loads to shortlist five people.
"""

from __future__ import annotations

import pytest

from fit_happens.schemas import (
    CandidateResult, CheckpointResult, Document, FitScore, StyleRead, Verdict,
)


def _candidate(cid: str, name: str = "") -> CandidateResult:
    return CandidateResult(
        candidate_id=cid, name=name,
        fit=FitScore(score=0.5, required_coverage=0.5, preferred_coverage=0.5),
        style=StyleRead(score=0.0, band="low", word_count=200),
        cp2=CheckpointResult(checkpoint="cp2_claims", verdict=Verdict.CLEAR),
        document=Document(source_path="x.pdf", text="", raw_text=""))


class TestACandidateIsAPerson:
    def test_the_id_hash_never_reaches_the_screen(self):
        """An applicant was listed as 'Naledi Dube 7B4F54'."""
        c = _candidate("naledi-dube-7b4f54", "Naledi Dube")
        assert c.display_name == "Naledi Dube"
        assert c.display_initials == "ND"

    def test_a_hash_is_stripped_even_without_an_application(self):
        assert _candidate("naledi-dube-7b4f54", "naledi-dube-7b4f54").display_name == "Naledi Dube"

    def test_a_bare_filename_is_labelled_honestly(self):
        """A CV added from the dashboard used to appear as '15118506', which reads like a bug
        rather than like a person we do not have a name for."""
        c = _candidate("15118506", "15118506")
        assert c.display_name == "Applicant 15118506"
        assert c.display_initials == "A"

    def test_underscored_filenames_still_read_as_names(self):
        assert _candidate("priya_raman", "priya_raman").display_name == "Priya Raman"

    def test_a_real_word_that_looks_like_hex_is_kept(self):
        """'Ada' and 'Bea' are hex-ish. Dropping a real surname would be worse than keeping a
        hash, so only short trailing tokens that are entirely hex digits are removed."""
        assert "Cabbage" in _candidate("x", "Ann Cabbage").display_name

    def test_missing_name_falls_back_to_the_id(self):
        assert _candidate("naledi-dube-7b4f54", "").display_name == "Naledi Dube"


class TestRoleLifecycle:
    def test_a_new_role_is_open(self, tmp_path, monkeypatch):
        import fit_happens.store as store
        monkeypatch.setattr(store, "RUNS", tmp_path)
        assert not store.Run("r").closed

    def test_closing_and_reopening(self, tmp_path, monkeypatch):
        import fit_happens.store as store
        monkeypatch.setattr(store, "RUNS", tmp_path)
        run = store.Run("r")
        run.set_closed(True)
        assert store.Run("r").closed
        run.set_closed(False)
        assert not store.Run("r").closed

    def test_closing_deletes_nothing(self, tmp_path, monkeypatch):
        """Applicants keep their pages, answers and consent choices - all of which the employer
        may be asked about later."""
        import fit_happens.store as store
        monkeypatch.setattr(store, "RUNS", tmp_path)
        run = store.Run("r")
        run.save_candidate(_candidate("someone", "Someone"))
        run.set_closed(True)
        assert run.candidate("someone") is not None

    def test_removing_a_candidate(self, tmp_path, monkeypatch):
        import fit_happens.store as store
        monkeypatch.setattr(store, "RUNS", tmp_path)
        run = store.Run("r")
        run.save_candidate(_candidate("dupe", "Dupe"))
        assert run.candidate("dupe") is not None
        run.delete_candidate("dupe")
        assert run.candidate("dupe") is None

    def test_removing_something_absent_does_not_explode(self, tmp_path, monkeypatch):
        import fit_happens.store as store
        monkeypatch.setattr(store, "RUNS", tmp_path)
        store.Run("r").delete_candidate("never-existed")


class TestBulkStaging:
    def test_several_people_move_in_one_action(self, tmp_path, monkeypatch):
        """Shortlisting five people used to be five page loads."""
        import fit_happens.stages as st
        monkeypatch.setattr(st, "DATA_DIR", tmp_path)
        store = st.StageStore("r")
        for cid in ("a", "b", "c"):
            store.set(cid, "shortlisted")
        assert all(store.load(cid).stage == "shortlisted" for cid in ("a", "b", "c"))

    def test_each_move_is_recorded_separately(self, tmp_path, monkeypatch):
        import fit_happens.stages as st
        monkeypatch.setattr(st, "DATA_DIR", tmp_path)
        store = st.StageStore("r")
        store.set("a", "reviewing")
        store.set("a", "shortlisted")
        assert [h["to"] for h in store.load("a").history] == ["reviewing", "shortlisted"]
