from datetime import date

import pytest
from doubles.project_board_test_doubles import (
    FakeProjectBoardClient, FakeProjectBoardClientFactory, ProjectItemFactory)

from agent_watch.api.project_board.models import NewSprintWeek, ProjectBoard, ProjectItem, SprintWeek
from agent_watch.api.project_board.roll_over_sprint import (
    SprintRolloverPlan, SprintRolloverResult, build_sprint_summary, plan_new_weeks, plan_sprint_rollover,
    roll_over_sprint)

FIRST_DAY_OF_WEEK_TWO: date = date(2026, 11, 23)


@pytest.fixture
def week_one_items(make_item: ProjectItemFactory, week_one: SprintWeek) -> list[ProjectItem]:
    return [
        make_item("unfinished", status="In Progress", week=week_one, assignee_logins=["Ernesto-B"], issue_number=4),
        make_item("finished", status="Done", week=week_one, assignee_logins=["joshuajipp"], issue_number=12),
        make_item("closed", status="Ready", week=week_one, issue_state="CLOSED", issue_number=13),
        make_item("backlog", status="Backlog", issue_number=1),
    ]


@pytest.fixture
def week_two_plan(project_board: ProjectBoard, week_one_items: list[ProjectItem]) -> SprintRolloverPlan:
    return plan_sprint_rollover(project_board, week_one_items, FIRST_DAY_OF_WEEK_TWO, 0)


def test_plan_carries_over_unfinished_items_and_lists_finished_ones(
        week_two_plan: SprintRolloverPlan, week_one: SprintWeek, week_two: SprintWeek) -> None:
    assert week_two_plan.target_week == week_two
    assert week_two_plan.previous_week == week_one
    assert [item.id for item in week_two_plan.carried_over_items] == ["unfinished"]
    assert [item.id for item in week_two_plan.finished_items] == ["finished", "closed"]
    assert [item.id for item in week_two_plan.this_week_items] == ["unfinished"]


def test_plan_during_a_break_targets_the_next_week(
        project_board: ProjectBoard, week_one_items: list[ProjectItem], week_two: SprintWeek,
        week_after_winter_break: SprintWeek) -> None:
    plan: SprintRolloverPlan = plan_sprint_rollover(project_board, week_one_items, date(2026, 12, 21), 0)

    assert plan.target_week == week_after_winter_break
    assert plan.previous_week == week_two


@pytest.mark.parametrize(("minimum_future_weeks", "expected_titles"), [
    (1, ["Week 3 (Nov 30)"]),
    (3, ["Week 3 (Nov 30)", "Week 4 (Dec 7)", "Week 5 (Dec 14)"]),
])
def test_plan_new_weeks_tops_up_to_the_minimum(week_one: SprintWeek, week_two: SprintWeek,
                                               minimum_future_weeks: int, expected_titles: list[str]) -> None:
    new_weeks: list[NewSprintWeek] = plan_new_weeks([week_one, week_two], FIRST_DAY_OF_WEEK_TWO, minimum_future_weeks)

    assert [week.title for week in new_weeks] == expected_titles
    assert new_weeks[0] == NewSprintWeek(title="Week 3 (Nov 30)", start_date=date(2026, 11, 30), duration_days=7)


def test_plan_new_weeks_adds_nothing_when_enough_remain(project_board: ProjectBoard) -> None:
    assert plan_new_weeks(project_board.weeks, date(2026, 11, 18), 2) == []


def test_summary_lists_finished_carried_over_and_people_without_work(week_two_plan: SprintRolloverPlan) -> None:
    summary: str = build_sprint_summary(week_two_plan, {"Ernesto-B", "joshuajipp", "graziamena"})

    assert summary.startswith("## Week 2 (Nov 23) has started")
    assert "**Finished in Week 1 (Nov 16)** (2)" in summary
    assert "- [#12](https://github.com/AgentWatchOrg/AgentWatch/issues/12) Title of finished (@joshuajipp)" in summary
    assert "**Carried over into Week 2 (Nov 23)** (1)" in summary
    assert "**No cards this week:** @graziamena, @joshuajipp" in summary


def test_summary_says_everyone_has_work_when_nobody_is_idle(week_two_plan: SprintRolloverPlan) -> None:
    assert "everyone has work" in build_sprint_summary(week_two_plan, {"Ernesto-B"})


def test_dry_run_builds_the_summary_without_changing_or_posting(
        make_fake_client: FakeProjectBoardClientFactory, week_one_items: list[ProjectItem]) -> None:
    client: FakeProjectBoardClient = make_fake_client(items=week_one_items, collaborator_logins={"joshuajipp"})

    result: SprintRolloverResult = roll_over_sprint(client, FIRST_DAY_OF_WEEK_TWO, 4, should_post_summary=True,
                                                    is_dry_run=True)

    assert result.summary is not None
    assert result.sprint_log_issue_number is None
    assert client.recorded_calls == []


def test_real_run_moves_cards_adds_weeks_and_posts_the_summary(
        make_fake_client: FakeProjectBoardClientFactory, week_one_items: list[ProjectItem]) -> None:
    client: FakeProjectBoardClient = make_fake_client(items=week_one_items, collaborator_logins={"joshuajipp"})

    result: SprintRolloverResult = roll_over_sprint(client, FIRST_DAY_OF_WEEK_TWO, 2, should_post_summary=True,
                                                    is_dry_run=False)

    assert result.sprint_log_issue_number == 99
    assert client.recorded_calls == [
        ("set_item_week", "unfinished", "week-2"),
        ("add_weeks", "Week 4 (Jan 11)"),
        ("find_or_create_issue", "Sprint Log"),
        ("comment_on_issue", "99"),
    ]


def test_run_without_summary_skips_posting(
        make_fake_client: FakeProjectBoardClientFactory, week_one_items: list[ProjectItem]) -> None:
    client: FakeProjectBoardClient = make_fake_client(items=week_one_items)

    result: SprintRolloverResult = roll_over_sprint(client, FIRST_DAY_OF_WEEK_TWO, 0, should_post_summary=False,
                                                    is_dry_run=False)

    assert result.summary is None
    assert client.recorded_calls == [("set_item_week", "unfinished", "week-2")]
