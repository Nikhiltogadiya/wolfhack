"""Deterministic career arithmetic. This is the code that exists because the model returned
years=2019.0 for "since 2019" on our very first extraction."""

from __future__ import annotations

from datetime import date

import pytest

from fit_happens.fit.derived import (
    career_start_year, leadership_roles, parse_when, total_experience_years,
)
from fit_happens.schemas import Employment, Span


def _e(title, start, end, employer="Acme"):
    return Employment(employer=employer, title=title, start=start, end=end, evidence=Span(text="x"))


@pytest.mark.parametrize("text,expected", [
    ("December 2014", date(2014, 12, 1)),
    ("Dec 2014", date(2014, 12, 1)),
    ("2014-12", date(2014, 12, 1)),
    ("12/2014", date(2014, 12, 1)),
    ("2014", date(2014, 1, 1)),
    ("January 1999", date(1999, 1, 1)),
    ("", None),
    (None, None),
    ("sometime in the nineties", None),   # must return None, never guess
])
def test_parse_when(text, expected):
    assert parse_when(text) == expected


def test_present_resolves_to_today():
    assert parse_when("present") == date.today()


def test_overlapping_roles_are_not_double_counted():
    """Counting roles separately would reward the exact pattern the bluff detector flags."""
    emp = [_e("Engineer", "2015", "2020"), _e("Consultant", "2017", "2020")]
    assert total_experience_years(emp) == pytest.approx(5.0, abs=0.1)


def test_adjacent_roles_sum():
    emp = [_e("Junior", "2010", "2015"), _e("Senior", "2015", "2020")]
    assert total_experience_years(emp) == pytest.approx(10.0, abs=0.1)


def test_gap_between_roles_is_not_counted():
    """A career break must not inflate experience - and must not be penalised either; it simply
    is not counted as time worked."""
    emp = [_e("A", "2005", "2010"), _e("B", "2015", "2020")]
    assert total_experience_years(emp) == pytest.approx(10.0, abs=0.1)


def test_career_start_is_the_earliest_role():
    assert career_start_year([_e("A", "2008", "2014"), _e("B", "1999", "2006")]) == 1999


def test_undated_roles_do_not_crash_or_count():
    assert total_experience_years([_e("A", None, None)]) == 0.0


class TestLeadership:
    @pytest.mark.parametrize("title", [
        "Engineering Manager", "Team Lead", "Head of Infrastructure",
        "IT Director", "Shift Supervisor", "Principal Engineer",
    ])
    def test_real_leadership_titles(self, title):
        assert leadership_roles([_e(title, "2015", "2020")])

    @pytest.mark.parametrize("title", [
        "Network Management System Engineer",   # from a real corpus resume
        "Configuration Manager Administrator",
        "Call Manager Specialist",
        "Endpoint Manager Analyst",
        "Help Desk Analyst",
    ])
    def test_product_names_containing_manager_are_not_leadership(self, title):
        """'Configuration Manager' is a Microsoft product, not a report line."""
        assert not leadership_roles([_e(title, "2015", "2020")])

    @pytest.mark.parametrize("title", [
        "Network Management System Engineer",     # real corpus title - manages no one
        "Product Lifecycle Management Analyst",
        "Risk Management Specialist",
        "Identity Management Engineer",
    ])
    def test_x_management_is_a_discipline_not_a_report_line(self, title):
        assert not leadership_roles([_e(title, "2015", "2020")])

    @pytest.mark.parametrize("title", [
        "Manager, IT Infrastructure",
        "Engineering Manager",
        "Head of Platform",
    ])
    def test_genuine_manager_titles_still_match(self, title):
        assert leadership_roles([_e(title, "2015", "2020")])
