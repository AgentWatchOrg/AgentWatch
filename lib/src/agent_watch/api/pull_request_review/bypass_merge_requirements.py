from agent_watch.api.pull_request_review.models import (
    ADMIN_PERMISSION, APPROVED_REVIEW_STATE, MERGE_REQUIREMENTS_BYPASS_LABEL, MERGE_REQUIREMENTS_BYPASS_MARKER,
    LabelEvent, MergeRequirementsBypassChange, MergeRequirementsBypassPlan, SubmittedReview)
from agent_watch.api.pull_request_review.pull_request_client import PullRequestClient

BYPASS_APPROVAL_BODY: str = (
    f"Approved because a repository admin added the `{MERGE_REQUIREMENTS_BYPASS_LABEL}` label. "
    f"Removing the label withdraws this approval.\n\n{MERGE_REQUIREMENTS_BYPASS_MARKER}")
BYPASS_APPROVAL_DISMISSAL_MESSAGE: str = (
    f"The `{MERGE_REQUIREMENTS_BYPASS_LABEL}` label is gone or was not added by a repository admin.")


def find_bypass_labeler_login(label_names: list[str], label_events: list[LabelEvent]) -> str | None:
    if MERGE_REQUIREMENTS_BYPASS_LABEL not in label_names:
        return None
    bypass_label_additions: list[LabelEvent] = [
        event for event in label_events if event.label_name == MERGE_REQUIREMENTS_BYPASS_LABEL and event.is_added]
    return bypass_label_additions[-1].actor_login if bypass_label_additions else None


def find_bypass_approval_ids(reviews: list[SubmittedReview]) -> list[int]:
    return [review.id for review in reviews
            if review.state == APPROVED_REVIEW_STATE and MERGE_REQUIREMENTS_BYPASS_MARKER in review.body]


def plan_merge_requirements_bypass(pull_request_number: int, label_names: list[str],
                                   labeled_by_login: str | None, labeler_permission: str | None,
                                   reviews: list[SubmittedReview]) -> MergeRequirementsBypassPlan:
    is_authorized: bool = labeled_by_login is not None and labeler_permission == ADMIN_PERMISSION
    bypass_approval_ids: list[int] = find_bypass_approval_ids(reviews)
    changes: list[MergeRequirementsBypassChange] = []
    if is_authorized and not bypass_approval_ids:
        changes.append(MergeRequirementsBypassChange.APPROVE)
    if not is_authorized and MERGE_REQUIREMENTS_BYPASS_LABEL in label_names:
        changes.append(MergeRequirementsBypassChange.REMOVE_UNAUTHORIZED_LABEL)
    if not is_authorized and bypass_approval_ids:
        changes.append(MergeRequirementsBypassChange.DISMISS_BYPASS_APPROVAL)
    return MergeRequirementsBypassPlan(
        pull_request_number=pull_request_number, labeled_by_login=labeled_by_login, is_authorized=is_authorized,
        changes=changes, bypass_approval_ids_to_dismiss=[] if is_authorized else bypass_approval_ids)


def load_merge_requirements_bypass_plan(client: PullRequestClient,
                                        pull_request_number: int) -> MergeRequirementsBypassPlan:
    label_names: list[str] = client.load_label_names(pull_request_number)
    labeled_by_login: str | None = find_bypass_labeler_login(
        label_names,
        client.load_label_events(pull_request_number) if MERGE_REQUIREMENTS_BYPASS_LABEL in label_names else [])
    labeler_permission: str | None = (
        client.load_repository_permission(labeled_by_login) if labeled_by_login else None)
    return plan_merge_requirements_bypass(pull_request_number, label_names, labeled_by_login, labeler_permission,
                                          client.load_reviews(pull_request_number))


def apply_merge_requirements_bypass(client: PullRequestClient, plan: MergeRequirementsBypassPlan) -> None:
    for change in plan.changes:
        if change is MergeRequirementsBypassChange.APPROVE:
            client.approve_pull_request(plan.pull_request_number, BYPASS_APPROVAL_BODY)
        elif change is MergeRequirementsBypassChange.REMOVE_UNAUTHORIZED_LABEL:
            client.remove_label(plan.pull_request_number, MERGE_REQUIREMENTS_BYPASS_LABEL)
        elif change is MergeRequirementsBypassChange.DISMISS_BYPASS_APPROVAL:
            for review_id in plan.bypass_approval_ids_to_dismiss:
                client.dismiss_review(plan.pull_request_number, review_id, BYPASS_APPROVAL_DISMISSAL_MESSAGE)


def bypass_merge_requirements(client: PullRequestClient, pull_request_number: int,
                              is_dry_run: bool) -> MergeRequirementsBypassPlan:
    plan: MergeRequirementsBypassPlan = load_merge_requirements_bypass_plan(client, pull_request_number)
    if not is_dry_run:
        apply_merge_requirements_bypass(client, plan)
    return plan
