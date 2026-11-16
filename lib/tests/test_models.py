from datetime import date

import pytest
from project_board_test_doubles import WEEK_ONE, WEEK_THREE, WEEK_TWO, make_board, make_item

from agent_watch.api.project_board.models import NoSprintWeekError


def test_sprint_week_contains_its_days_but_not_the_next_start() -> None:
    assert WEEK_ONE.contains(date(2026, 11, 16))
    assert WEEK_ONE.contains(date(2026, 11, 22))
    assert not WEEK_ONE.contains(date(2026, 11, 23))
    assert WEEK_ONE.end_date == date(2026, 11, 23)


def test_current_or_next_week_returns_the_week_containing_today() -> None:
    assert make_board().current_or_next_week(date(2026, 11, 25)) == WEEK_TWO


def test_current_or_next_week_returns_the_next_week_during_a_break() -> None:
    assert make_board().current_or_next_week(date(2026, 12, 20)) == WEEK_THREE


def test_current_or_next_week_raises_when_no_weeks_remain() -> None:
    with pytest.raises(NoSprintWeekError):
        make_board().current_or_next_week(date(2027, 6, 1))


def test_item_is_finished_when_done_or_closed() -> None:
    assert make_item("done", status="Done").is_finished
    assert make_item("closed", issue_state="CLOSED").is_finished
    assert make_item("merged", issue_state="MERGED").is_closed
    assert not make_item("ready").is_finished
