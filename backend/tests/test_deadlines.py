from datetime import date

import pytest

from contextos.tasks.deadlines import find_dates, find_deadlines, parse_date

TODAY = date(2026, 10, 15)


@pytest.mark.parametrize("text, expected", [
    ("2026-11-03", date(2026, 11, 3)),
    ("12/11/2026", date(2026, 11, 12)),       # day first by default
    ("12.11.26", date(2026, 11, 12)),
    ("28th October 2026", date(2026, 10, 28)),
    ("3 Sept 2026", date(2026, 9, 3)),
    ("October 30, 2026", date(2026, 10, 30)),
    ("Nov 5th", date(2026, 11, 5)),            # no year: next occurrence
    ("5 Jan", date(2027, 1, 5)),               # already passed this year -> next year
    ("10/25/2026", date(2026, 10, 25)),        # only valid as month-first
])
def test_parse_date_formats(text, expected):
    assert parse_date(text, TODAY) == expected


def test_month_first_order():
    assert parse_date("04/05/2026", TODAY, order="MDY") == date(2026, 4, 5)
    assert parse_date("04/05/2026", TODAY, order="DMY") == date(2026, 5, 4)


def test_invalid_dates_are_ignored():
    assert find_dates("31/02/2026 and 45/13/2026", TODAY) == []


def test_only_dates_next_to_deadline_words_count():
    text = (
        "Database Management Systems - Assignment 2\n"
        "Issued on 01/10/2026\n"
        "Exam scheduled for 20/12/2026\n"
        "Last date for submission: 28th October 2026\n"
    )
    found = find_deadlines(text, TODAY, default_title="DBMS Assignment 2")
    assert [(d.title, d.due) for d in found] == [("DBMS Assignment 2", date(2026, 10, 28))]


def test_date_on_the_line_after_the_keyword():
    found = find_deadlines("Submission deadline:\n5 November 2026", TODAY)
    assert found[0].due == date(2026, 11, 5)


def test_past_deadlines_are_dropped():
    assert find_deadlines("Due date: 01/09/2026", TODAY) == []
