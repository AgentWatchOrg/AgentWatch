import pytest
from doubles.pull_request_review_test_doubles import FakePullRequestClient

from agent_watch.api.pull_request_review.bypass_merge_requirements import (
    BYPASS_APPROVAL_BODY, apply_merge_requirements_bypass, bypass_merge_requirements, find_bypass_approval_ids,
    find_bypass_labeler_login, load_merge_requirements_bypass_plan, plan_merge_requirements_bypass)
from agent_watch.api.pull_request_review.models import (
    MERGE_REQUIREMENTS_BYPASS_LABEL, LabelEvent, MergeRequirementsBypassChange, MergeRequirementsBypassPlan,
    PullRequest, SubmittedReview)

BYPASS_LABEL: str = MERGE_REQUIREMENTS_BYPASS_LABEL


@pytest.fixture
def bypass_approval() -> SubmittedReview:
    return SubmittedReview(id=501, state="APPROVED", body=BYPASS_APPROVAL_BODY)


@pytest.fixture
def fake_client(pull_request: PullRequest) -> FakePullRequestClient:
    return FakePullRequestClient(pull_request, [])


@pytest.mark.parametrize(("label_names", "label_events", "expected_login"), [
    ([BYPASS_LABEL], [LabelEvent(BYPASS_LABEL, True, "joshuajipp")], "joshuajipp"),
    ([BYPASS_LABEL], [LabelEvent(BYPASS_LABEL, True, "Ernesto-B"), LabelEvent(BYPASS_LABEL, False, "Ernesto-B"),
                      LabelEvent(BYPASS_LABEL, True, "joshuajipp")], "joshuajipp"),
    ([BYPASS_LABEL], [LabelEvent("p1", True, "joshuajipp")], None),
    (["p1"], [LabelEvent(BYPASS_LABEL, True, "joshuajipp")], None),
], ids=["added once", "re-added by someone else", "no addition event", "label since removed"])
def test_find_bypass_labeler_login(label_names: list[str], label_events: list[LabelEvent],
                                   expected_login: str | None) -> None:
    assert find_bypass_labeler_login(label_names, label_events) == expected_login


def test_find_bypass_approval_ids_ignores_human_and_dismissed_reviews(bypass_approval: SubmittedReview) -> None:
    reviews: list[SubmittedReview] = [
        bypass_approval, SubmittedReview(id=502, state="APPROVED", body="Looks good"),
        SubmittedReview(id=503, state="DISMISSED", body=BYPASS_APPROVAL_BODY)]

    assert find_bypass_approval_ids(reviews) == [501]


@pytest.mark.parametrize(("label_names", "labeled_by_login", "permission", "has_bypass_approval", "is_authorized",
                          "expected_changes"), [
    ([BYPASS_LABEL], "joshuajipp", "admin", False, True, [MergeRequirementsBypassChange.APPROVE]),
    ([BYPASS_LABEL], "joshuajipp", "admin", True, True, []),
    ([BYPASS_LABEL], "Ernesto-B", "write", False, False, [MergeRequirementsBypassChange.REMOVE_UNAUTHORIZED_LABEL]),
    ([BYPASS_LABEL], "Ernesto-B", "write", True, False,
     [MergeRequirementsBypassChange.REMOVE_UNAUTHORIZED_LABEL, MergeRequirementsBypassChange.DISMISS_BYPASS_APPROVAL]),
    ([], None, None, True, False, [MergeRequirementsBypassChange.DISMISS_BYPASS_APPROVAL]),
    ([], None, None, False, False, []),
], ids=["admin adds label", "admin label already approved", "non-admin adds label",
        "non-admin re-adds after admin approval", "label removed", "no label"])
def test_plan_merge_requirements_bypass(label_names: list[str], labeled_by_login: str | None,
                                        permission: str | None, has_bypass_approval: bool, is_authorized: bool,
                                        expected_changes: list[MergeRequirementsBypassChange],
                                        bypass_approval: SubmittedReview) -> None:
    plan: MergeRequirementsBypassPlan = plan_merge_requirements_bypass(
        7, label_names, labeled_by_login, permission, [bypass_approval] if has_bypass_approval else [])

    assert plan.is_authorized is is_authorized
    assert plan.changes == expected_changes
    assert plan.bypass_approval_ids_to_dismiss == ([501] if has_bypass_approval and not is_authorized else [])


def test_load_plan_only_looks_up_events_and_permission_when_the_label_is_present(
        fake_client: FakePullRequestClient) -> None:
    fake_client.label_names = ["p1"]

    plan: MergeRequirementsBypassPlan = load_merge_requirements_bypass_plan(fake_client, 7)

    assert not plan.is_authorized
    assert fake_client.recorded_calls == []


def test_load_plan_checks_the_labeler_is_an_admin(fake_client: FakePullRequestClient) -> None:
    fake_client.label_names = [BYPASS_LABEL]
    fake_client.label_events = [LabelEvent(BYPASS_LABEL, True, "joshuajipp")]
    fake_client.permissions_by_login = {"joshuajipp": "admin"}

    plan: MergeRequirementsBypassPlan = load_merge_requirements_bypass_plan(fake_client, 7)

    assert plan.is_authorized and plan.labeled_by_login == "joshuajipp"
    assert ("load_repository_permission", "joshuajipp") in fake_client.recorded_calls


def test_apply_runs_each_planned_change(fake_client: FakePullRequestClient) -> None:
    plan: MergeRequirementsBypassPlan = MergeRequirementsBypassPlan(
        pull_request_number=7, labeled_by_login="Ernesto-B", is_authorized=False,
        changes=[MergeRequirementsBypassChange.REMOVE_UNAUTHORIZED_LABEL,
                 MergeRequirementsBypassChange.DISMISS_BYPASS_APPROVAL],
        bypass_approval_ids_to_dismiss=[501, 502])

    apply_merge_requirements_bypass(fake_client, plan)

    assert fake_client.recorded_calls == [("remove_label", BYPASS_LABEL), ("dismiss_review", "501"),
                                          ("dismiss_review", "502")]


@pytest.mark.parametrize(("is_dry_run", "expected_approvals"), [
    (True, []),
    (False, [("approve_pull_request", "7")]),
], ids=["dry run", "real run"])
def test_bypass_merge_requirements_approves_only_outside_dry_run(
        fake_client: FakePullRequestClient, is_dry_run: bool, expected_approvals: list[tuple[str, ...]]) -> None:
    fake_client.label_names = [BYPASS_LABEL]
    fake_client.label_events = [LabelEvent(BYPASS_LABEL, True, "joshuajipp")]
    fake_client.permissions_by_login = {"joshuajipp": "admin"}

    plan: MergeRequirementsBypassPlan = bypass_merge_requirements(fake_client, 7, is_dry_run)

    assert plan.changes == [MergeRequirementsBypassChange.APPROVE]
    assert [call for call in fake_client.recorded_calls if call[0] == "approve_pull_request"] == expected_approvals
