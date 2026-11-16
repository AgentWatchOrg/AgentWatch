from datetime import date

import pytest
from doubles.project_board_test_doubles import ProjectItemFactory

from agent_watch.api.project_board.models import NoSprintWeekError, ProjectBoard, ProjectItem, SprintWeek


@pytest.mark.parametrize(("day", "is_inside_week"), [
    (date(2026, 11, 16), True),
    (date(2026, 11, 22), True),
    (date(2026, 11, 23), False),
    (date(2026, 11, 15), False),
])
def test_sprint_week_contains_only_its_own_days(week_one: SprintWeek, day: date, is_inside_week: bool) -> None:
    assert week_one.contains(day) is is_inside_week


def test_sprint_week_ends_after_its_duration(week_one: SprintWeek) -> None:
    assert week_one.end_date == date(2026, 11, 23)


@pytest.mark.parametrize(("today", "expected_week_fixture"), [
    (date(2026, 11, 25), "week_two"),
    (date(2026, 12, 20), "week_after_winter_break"),
], ids=["during a week", "during a break"])
def test_current_or_next_week(project_board: ProjectBoard, request: pytest.FixtureRequest, today: date,
                              expected_week_fixture: str) -> None:
    assert project_board.current_or_next_week(today) == request.getfixturevalue(expected_week_fixture)


def test_current_or_next_week_raises_when_no_weeks_remain(project_board: ProjectBoard) -> None:
    with pytest.raises(NoSprintWeekError):
        project_board.current_or_next_week(date(2027, 6, 1))


@pytest.mark.parametrize(("status", "issue_state", "is_finished", "is_closed"), [
    ("Done", "OPEN", True, False),
    ("Ready", "CLOSED", True, True),
    ("Ready", "MERGED", True, True),
    ("Ready", "OPEN", False, False),
])
def test_item_is_finished_when_done_or_closed(make_item: ProjectItemFactory, status: str, issue_state: str,
                                               is_finished: bool, is_closed: bool) -> None:
    item: ProjectItem = make_item("item", status=status, issue_state=issue_state)

    assert item.is_finished is is_finished
    assert item.is_closed is is_closed
