from datetime import date

from project_board_test_doubles import WEEK_ONE, WEEK_THREE, WEEK_TWO, FakeProjectBoardClient, make_board, make_item

from agent_watch.api.project_board.models import NewSprintWeek, ProjectItem
from agent_watch.api.project_board.roll_over_sprint import (
    SprintRolloverPlan, SprintRolloverResult, build_sprint_summary, plan_new_weeks, plan_sprint_rollover,
    roll_over_sprint)

FIRST_DAY_OF_WEEK_TWO: date = date(2026, 11, 23)


def make_week_one_items() -> list[ProjectItem]:
    return [
        make_item("unfinished", status="In Progress", week=WEEK_ONE, assignee_logins=["Ernesto-B"], issue_number=4),
        make_item("finished", status="Done", week=WEEK_ONE, assignee_logins=["joshuajipp"], issue_number=12),
        make_item("closed", status="Ready", week=WEEK_ONE, issue_state="CLOSED", issue_number=13),
        make_item("backlog", status="Backlog", issue_number=1),
    ]


def test_plan_carries_over_unfinished_items_and_lists_finished_ones() -> None:
    plan: SprintRolloverPlan = plan_sprint_rollover(make_board(), make_week_one_items(), FIRST_DAY_OF_WEEK_TWO, 0)

    assert plan.target_week == WEEK_TWO
    assert plan.previous_week == WEEK_ONE
    assert [item.id for item in plan.carried_over_items] == ["unfinished"]
    assert [item.id for item in plan.finished_items] == ["finished", "closed"]
    assert [item.id for item in plan.this_week_items] == ["unfinished"]


def test_plan_during_a_break_targets_the_next_week() -> None:
    plan: SprintRolloverPlan = plan_sprint_rollover(make_board(), make_week_one_items(), date(2026, 12, 21), 0)

    assert plan.target_week == WEEK_THREE
    assert plan.previous_week == WEEK_TWO


def test_plan_new_weeks_tops_up_to_the_minimum() -> None:
    new_weeks: list[NewSprintWeek] = plan_new_weeks([WEEK_ONE, WEEK_TWO], FIRST_DAY_OF_WEEK_TWO, 3)

    assert new_weeks == [
        NewSprintWeek(title="Week 3 (Nov 30)", start_date=date(2026, 11, 30), duration_days=7),
        NewSprintWeek(title="Week 4 (Dec 7)", start_date=date(2026, 12, 7), duration_days=7),
        NewSprintWeek(title="Week 5 (Dec 14)", start_date=date(2026, 12, 14), duration_days=7),
    ]


def test_plan_new_weeks_adds_nothing_when_enough_remain() -> None:
    assert plan_new_weeks([WEEK_ONE, WEEK_TWO, WEEK_THREE], date(2026, 11, 18), 2) == []


def test_summary_lists_finished_carried_over_and_people_without_work() -> None:
    plan: SprintRolloverPlan = plan_sprint_rollover(make_board(), make_week_one_items(), FIRST_DAY_OF_WEEK_TWO, 0)

    summary: str = build_sprint_summary(plan, {"Ernesto-B", "joshuajipp", "graziamena"})

    assert summary.startswith("## Week 2 (Nov 23) has started")
    assert "**Finished in Week 1 (Nov 16)** (2)" in summary
    assert "- [#12](https://github.com/AgentWatchOrg/AgentWatch/issues/12) Title of finished (@joshuajipp)" in summary
    assert "**Carried over into Week 2 (Nov 23)** (1)" in summary
    assert "**No cards this week:** @graziamena, @joshuajipp" in summary


def test_summary_says_everyone_has_work_when_nobody_is_idle() -> None:
    plan: SprintRolloverPlan = plan_sprint_rollover(make_board(), make_week_one_items(), FIRST_DAY_OF_WEEK_TWO, 0)

    assert "everyone has work" in build_sprint_summary(plan, {"Ernesto-B"})


def test_dry_run_builds_the_summary_without_changing_or_posting() -> None:
    client: FakeProjectBoardClient = FakeProjectBoardClient(make_board(), make_week_one_items(), [], {"joshuajipp"})

    result: SprintRolloverResult = roll_over_sprint(client, FIRST_DAY_OF_WEEK_TWO, 4, should_post_summary=True,
                                                    is_dry_run=True)

    assert result.summary is not None
    assert result.sprint_log_issue_number is None
    assert client.recorded_calls == []


def test_real_run_moves_cards_adds_weeks_and_posts_the_summary() -> None:
    client: FakeProjectBoardClient = FakeProjectBoardClient(make_board(), make_week_one_items(), [], {"joshuajipp"})

    result: SprintRolloverResult = roll_over_sprint(client, FIRST_DAY_OF_WEEK_TWO, 2, should_post_summary=True,
                                                    is_dry_run=False)

    assert result.sprint_log_issue_number == 99
    assert client.recorded_calls == [
        ("set_item_week", "unfinished", "week-2"),
        ("add_weeks", "Week 4 (Jan 11)"),
        ("find_or_create_issue", "Sprint Log"),
        ("comment_on_issue", "99"),
    ]


def test_run_without_summary_skips_posting() -> None:
    client: FakeProjectBoardClient = FakeProjectBoardClient(make_board(), make_week_one_items(), [])

    result: SprintRolloverResult = roll_over_sprint(client, FIRST_DAY_OF_WEEK_TWO, 0, should_post_summary=False,
                                                    is_dry_run=False)

    assert result.summary is None
    assert client.recorded_calls == [("set_item_week", "unfinished", "week-2")]
