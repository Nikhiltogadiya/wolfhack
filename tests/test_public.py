"""The candidate side of the marketplace.

Found by opening the site as a candidate rather than curling it: `/` was the recruiter's
dashboard, so an applicant landed on other applicants' names and fit scores, and every
recruiter page answered 200 with no credentials. There was also no way to apply at all -
`/jobs`, `/apply` and `/careers` were 404. That is the whole missing half of a marketplace.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fit_happens.candidate.applications import candidate_id_for, looks_like_email
from fit_happens.web import auth
from fit_happens.web.app import app

client = TestClient(app)


class TestTheFrontDoorIsPublic:
    def test_root_is_not_the_recruiter_dashboard(self):
        """The defect that started this: a candidate landed on the hiring team's dashboard."""
        body = client.get("/").text
        assert "I'm looking for work" in body
        assert "Hiring overview" not in body
        assert "Fit score" not in body

    def test_root_leaks_no_applicant_names(self):
        body = client.get("/").text
        for name in ("Priya Raman", "Amara Osei", "Marcus Webb", "Daniel Kowalski"):
            assert name not in body, f"{name} leaked onto the public landing page"

    @pytest.mark.parametrize("path", ["/", "/jobs", "/track"])
    def test_public_pages_answer_without_credentials(self, path):
        assert client.get(path).status_code == 200

    def test_the_landing_offers_both_doors(self):
        body = client.get("/").text
        assert "I'm looking for work" in body and "I'm hiring" in body


class TestFindingAndReadingAJob:
    def test_the_board_lists_open_roles(self):
        assert client.get("/jobs").status_code == 200

    def test_a_job_page_shows_the_advert_and_our_read_of_it(self):
        body = client.get("/jobs/demo").text
        assert "How specific this advert is" in body
        assert "The advert, as published" in body

    def test_private_preferences_are_never_shown_to_candidates(self):
        """Internal criteria are scored but are the employer's business. Leaking them here
        would tell every applicant exactly what to write."""
        body = client.get("/jobs/demo").text
        assert "ISO 27001 audit next year" not in body
        assert "PRIVATE" not in body

    def test_a_missing_job_is_a_friendly_404(self):
        r = client.get("/jobs/no-such-role")
        assert r.status_code == 404
        assert "no longer listed" in r.text


class TestApplying:
    def test_the_form_asks_for_three_things_and_no_account(self):
        body = client.get("/jobs/demo/apply").text
        assert 'name="name"' in body and 'name="email"' in body and 'name="cv"' in body
        assert "No account" in body

    @pytest.mark.parametrize("data,expected", [
        ({"name": "", "email": "a@b.co"}, "need a name"),
        ({"name": "Someone", "email": "not-an-email"}, "does not look right"),
        ({"name": "Someone", "email": "a@b.co"}, "attach your CV"),
    ])
    def test_bad_applications_explain_what_is_wrong(self, data, expected):
        r = client.post("/jobs/demo/apply", data=data)
        assert r.status_code == 400
        assert expected in r.text

    def test_a_rejected_application_keeps_what_was_typed(self):
        """Clearing the form and making them start again is the worst possible reply."""
        r = client.post("/jobs/demo/apply", data={"name": "Sam Okafor", "email": "bad"})
        assert "Sam Okafor" in r.text


class TestIdentity:
    def test_applicants_are_people_not_filenames(self):
        """Uploaded CVs were named after the file, so someone appeared in the dashboard as
        '15118506'."""
        cid = candidate_id_for("Naledi Dube", "naledi@example.com")
        assert cid.startswith("naledi-dube-")

    def test_the_same_name_with_a_different_email_is_a_different_person(self):
        assert (candidate_id_for("Sam Smith", "a@x.com")
                != candidate_id_for("Sam Smith", "b@x.com"))

    def test_the_same_person_applying_twice_keeps_one_identity(self):
        assert (candidate_id_for("Sam Smith", "a@x.com")
                == candidate_id_for("sam smith", "A@X.com"))

    @pytest.mark.parametrize("email,valid", [
        ("me@example.com", True), ("a@b.co", True),
        ("not-an-email", False), ("x@y", False), ("", False), ("a b@c.com", False),
    ])
    def test_email_validation(self, email, valid):
        assert looks_like_email(email) is valid


class TestTrackingALostLink:
    def test_an_unknown_email_says_so_kindly(self):
        body = client.get("/track", params={"email": "nobody@nowhere.test"}).text
        assert "Nothing found for that address" in body

    def test_the_form_is_shown_before_any_search(self):
        body = client.get("/track").text
        assert "Nothing found" not in body


class TestTheHiringGate:
    def test_with_no_passcode_the_area_is_open_and_says_so(self, monkeypatch):
        """A lock that is silently unlocked is worse than a visible absence of one."""
        monkeypatch.delenv(auth.ENV_VAR, raising=False)
        assert not auth.configured()
        assert "This area is unprotected" in client.get("/hiring").text

    def test_a_configured_passcode_is_enforced(self, monkeypatch):
        monkeypatch.setenv(auth.ENV_VAR, "letmein")
        assert auth.configured()
        assert auth.check("letmein")
        assert not auth.check("wrong")
        assert not auth.check("")

    def test_an_unsigned_visitor_is_sent_to_sign_in(self, monkeypatch):
        monkeypatch.setenv(auth.ENV_VAR, "letmein")
        r = TestClient(app, follow_redirects=False).get("/hiring")
        assert r.status_code == 303
        assert "/hiring/sign-in" in r.headers["location"]

    def test_a_wrong_passcode_is_refused_at_the_form(self, monkeypatch):
        monkeypatch.setenv(auth.ENV_VAR, "letmein")
        r = client.post("/hiring/sign-in", data={"passcode": "nope", "next": "/hiring"})
        assert r.status_code == 401
        assert "not right" in r.text

    def test_a_dotenv_passcode_is_actually_read(self, tmp_path, monkeypatch):
        """A .env was created with the passcode in it and nothing read it, so the area stayed
        open while it looked configured. A setting that silently does nothing is the worst
        kind, and this one guards applicants' files."""
        monkeypatch.delenv(auth.ENV_VAR, raising=False)
        env = tmp_path / ".env"
        env.write_text(f"{auth.ENV_VAR}=from-the-file\n")
        from dotenv import load_dotenv

        load_dotenv(env, override=False)
        assert auth.configured()
        assert auth.check("from-the-file")


def test_the_review_queue_never_selects_on_style_alone():
    """Hard rules 3 and 9 are enforced in the engine and were then handed back in the UI: the
    "Needs a human" filter read `c.style.band != "low"`, so a CV that merely reads as polished,
    with zero authenticity flags, was routed to a human on prose alone. The engine being right
    does not help when the only surface a recruiter acts on is wrong.

    Exercised against candidates rather than by grepping the source, because a source grep
    answers "does this word appear" - which a passing comment would break.
    """
    from fit_happens.schemas import CheckpointResult, StyleRead, Verdict
    from fit_happens.web.app import needs_a_human

    class C:
        def __init__(self, band, verdict):
            self.style = StyleRead(score=1.0 if band == "high" else 0.0, band=band)
            self.cp2 = CheckpointResult(checkpoint="cp2_claims", verdict=verdict)

    # the whole point: maximum style, no authenticity flags, still not selected.
    # both non-low bands, because the old predicate was `band != "low"`.
    assert not needs_a_human(C("high", Verdict.INCONCLUSIVE))
    assert not needs_a_human(C("grey", Verdict.INCONCLUSIVE))
    assert not needs_a_human(C("high", Verdict.CLEAR))
    # and a real corroborated flag is selected regardless of how it reads
    assert needs_a_human(C("low", Verdict.FLAG_FOR_HUMAN))
    assert needs_a_human(C("high", Verdict.FLAG_FOR_HUMAN))


def test_a_mistyped_role_url_creates_no_directory(tmp_path, monkeypatch):
    """`tasks._path` called mkdir on every access, including from reads, so simply polling
    the status endpoint for a role that does not exist created it. `store.Run`'s docstring
    records this being fixed there - "a crawler or a mistyped URL would litter the data
    directory" - and the tasks module quietly reintroduced it."""
    from fit_happens.web import tasks

    monkeypatch.setattr(tasks, "DATA_DIR", tmp_path)

    tasks.pending("no-such-role")
    tasks.recent("no-such-role")
    tasks.clear_finished("no-such-role")

    assert not (tmp_path / "runs" / "no-such-role").exists(), (
        "reading a nonexistent role must not create its directory")


class TestUploadLimits:
    """`accept=".pdf,.docx,.txt"` on the file input is a picker hint, not a constraint. The
    endpoint took anything, streamed the whole body to disk with copyfileobj, and then started
    a paid LLM pipeline per file - on a route that is public."""

    def _upload(self, name: str, data: bytes, tmp_path):
        from fit_happens.web.app import _save_upload

        class _Upload:
            filename = name

            def __init__(self, blob):
                import io

                self.file = io.BytesIO(blob)

        target = tmp_path / "out"
        return _save_upload(_Upload(data), target), target

    def test_a_wrong_type_is_refused_without_touching_disk(self, tmp_path):
        problem, target = self._upload("payload.sh", b"#!/bin/sh\necho hi\n", tmp_path)
        assert "PDF, DOCX and TXT" in problem
        assert not target.exists()

    def test_an_oversized_file_is_abandoned_not_truncated(self, tmp_path):
        from fit_happens.web.app import MAX_CV_BYTES

        problem, target = self._upload("big.pdf", b"x" * (MAX_CV_BYTES + 1024), tmp_path)
        assert "over" in problem
        # deleted, not left truncated: a truncated CV would be scored as the whole document
        assert not target.exists()

    def test_an_empty_file_is_refused(self, tmp_path):
        problem, target = self._upload("nothing.pdf", b"", tmp_path)
        assert "empty" in problem
        assert not target.exists()

    def test_a_real_cv_still_goes_through(self, tmp_path):
        problem, target = self._upload("cv.pdf", b"%PDF-1.4 plausible enough", tmp_path)
        assert problem == ""
        assert target.exists() and target.read_bytes().startswith(b"%PDF")
