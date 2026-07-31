# tests/unit/test_local_nl_extract.py
# Unit tests for the regex/keyword-based natural-language fallback
# extractor used when Gemini is unavailable or Local-Only Mode is on.

from src.app_utils.local_nl_extract import extract_metrics_from_text


def test_name_not_taken_from_sentence_starter():
    """Regression: the name must not be assumed to be the first word --
    "This week, Arjun completed..." used to extract "This" as the name."""
    result = extract_metrics_from_text(
        "This week, Arjun completed 5 tasks, latency was 3.2 hours, "
        "had 1 sick day, and 0 night logins."
    )
    assert result["employee_name"] == "Arjun"
    assert result["tasks_completed"] == 5
    assert result["avg_response_time_hours"] == 3.2
    assert result["sick_days"] == 1
    assert result["after_hours_logins"] == 0


def test_name_strips_possessive_suffix():
    """ "Ravi's accuracy dropped..." must extract "Ravi", not "Ravi's"."""
    result = extract_metrics_from_text(
        "Ravi's accuracy dropped to 72% and he logged in at night four times."
    )
    assert result["employee_name"] == "Ravi"
    assert result["task_accuracy"] == 72
    assert result["after_hours_logins"] == 4


def test_name_skips_leading_date_possessive():
    """A leading capitalized day-of-week possessive ("Monday's") must not be
    mistaken for the employee's name."""
    result = extract_metrics_from_text(
        "During Monday's review, Karthik seemed burnt out -- he called in "
        "sick twice and only delivered two tasks."
    )
    assert result["employee_name"] == "Karthik"
    assert result["sick_days"] == 2
    assert result["tasks_completed"] == 2
    assert result["sentiment"] == "Negative"


def test_word_numbers_are_understood():
    result = extract_metrics_from_text(
        "Priya finished three tasks and took no sick days, worked 42 hours this week."
    )
    assert result["employee_name"] == "Priya"
    assert result["tasks_completed"] == 3
    assert result["sick_days"] == 0
    assert result["weekly_hours"] == 42


def test_logged_in_does_not_leak_into_weekly_hours():
    """Regression: "logged in at night" used to also match the generic
    "logged" weekly-hours keyword, wrongly setting weekly_hours instead of
    after_hours_logins."""
    result = extract_metrics_from_text(
        "Ravi's accuracy dropped to 72% and he logged in at night four times."
    )
    assert result["weekly_hours"] == 40  # default, not leaked from "logged"
    assert result["after_hours_logins"] == 4


def test_worked_late_maps_to_after_hours_not_weekly_hours():
    """Regression: "worked late" used to be picked up by the generic
    "worked" weekly-hours keyword instead of signaling after-hours lateness."""
    result = extract_metrics_from_text(
        "Meena worked late several nights and seemed withdrawn during our chat."
    )
    assert result["weekly_hours"] == 40  # default, not misattributed
    assert result["after_hours_logins"] == 3
    assert result["sentiment"] == "Withdrawn"


def test_defaults_when_nothing_found():
    # No capitalized word at all -- exercises the "no name found" path.
    # (A capitalized sentence-starter with no dictionary to check against is
    # an inherent limitation of a lightweight heuristic, not something this
    # covers -- see test_name_not_taken_from_sentence_starter for the cases
    # this parser is actually expected to get right.)
    result = extract_metrics_from_text("everything is fine, nothing to report.")
    assert result["employee_name"] == "Unknown"
    assert result["tasks_completed"] == 0
    assert result["sentiment"] == "Neutral"
