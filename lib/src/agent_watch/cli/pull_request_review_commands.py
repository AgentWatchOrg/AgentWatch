import logging
from pathlib import Path

import click

from agent_watch.api.github_client import GitHubClient
from agent_watch.api.pull_request_review.bypass_merge_requirements import (
    bypass_merge_requirements, load_merge_requirements_bypass_plan)
from agent_watch.api.pull_request_review.check_ticket_reference import check_ticket_reference
from agent_watch.api.pull_request_review.models import (
    DEFAULT_REVIEW_MODEL, MAXIMUM_AGENT_TURNS, MERGE_REQUIREMENTS_BYPASS_LABEL, MergeRequirementsBypassPlan,
    PlannedReviewComment, PullRequestReviewResult, TicketReferenceCheck)
from agent_watch.api.pull_request_review.pull_request_client import PullRequestClient
from agent_watch.api.pull_request_review.review_pull_request import review_pull_request

logger: logging.Logger = logging.getLogger(__name__)


@click.group("pull-request-review", help="Review pull requests with a Claude agent.")
def pull_request_review() -> None:
    pass


@pull_request_review.command("review", help="Review one pull request and post new findings as comments.")
@click.option("--github-token", envvar="GITHUB_TOKEN", required=True,
              help="Token that can read the repository and write pull request comments. Env: GITHUB_TOKEN")
@click.option("--repository", envvar="GITHUB_REPOSITORY", default="AgentWatchOrg/AgentWatch", show_default=True)
@click.option("--pull-request-number", envvar="PULL_REQUEST_NUMBER", type=int, required=True)
@click.option("--repository-directory", envvar="REPOSITORY_DIRECTORY", default=".", show_default=True,
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Checkout of the pull request head. Env: REPOSITORY_DIRECTORY")
@click.option("--model", envvar="PULL_REQUEST_REVIEWER_MODEL", default=DEFAULT_REVIEW_MODEL, show_default=True)
@click.option("--maximum-agent-turns", envvar="MAXIMUM_AGENT_TURNS", default=MAXIMUM_AGENT_TURNS, show_default=True)
@click.option("--dry-run/--no-dry-run", "is_dry_run", envvar="IS_DRY_RUN", default=False,
              help="Print planned comments without posting them. Env: IS_DRY_RUN")
def review_command(github_token: str, repository: str, pull_request_number: int, repository_directory: Path,
                   model: str, maximum_agent_turns: int, is_dry_run: bool) -> None:
    try:
        # The Claude Agent SDK is an optional extra; other commands must work without it.
        from agent_watch.api.pull_request_review.review_agent_client import ClaudeReviewAgentClient
    except ImportError as error:
        raise click.ClickException(
            "The review command needs the Claude Agent SDK: pip install 'agent-watch[pull-request-review]'") from error
    result: PullRequestReviewResult = review_pull_request(
        PullRequestClient(GitHubClient(github_token), repository),
        ClaudeReviewAgentClient(model, maximum_agent_turns, repository_directory.resolve()),
        pull_request_number, is_dry_run)
    if result.plan is None or result.agent_run is None:
        logger.info(f"Skipped {repository}#{pull_request_number}: draft pull request")
        return
    for comment in result.plan.comments:
        logger.info(format_planned_comment(comment))
    logger.info(f"{len(result.plan.comments)} new finding(s), {len(result.plan.skipped_duplicate_findings)} "
               f"already raised, {result.agent_run.turn_count} agent turn(s)"
               f"{' (dry run)' if is_dry_run else ''}")
    if result.summary_comment_url:
        logger.info(f"Summary: {result.summary_comment_url}")

@pull_request_review.command("check-ticket-reference",
                             help="Fail unless the description has 'Closes #N' or 'Part of #N' for an existing issue.")
@click.option("--github-token", envvar="GITHUB_TOKEN", required=True, help="Env: GITHUB_TOKEN")
@click.option("--repository", envvar="GITHUB_REPOSITORY", default="AgentWatchOrg/AgentWatch", show_default=True)
@click.option("--pull-request-number", envvar="PULL_REQUEST_NUMBER", type=int, required=True)
def check_ticket_reference_command(github_token: str, repository: str, pull_request_number: int) -> None:
    result: TicketReferenceCheck = check_ticket_reference(
        PullRequestClient(GitHubClient(github_token), repository), pull_request_number)
    for missing_issue_number in result.missing_issue_numbers:
        logger.error(f"#{missing_issue_number} does not exist in {repository}.")
    for pull_request_reference in result.pull_request_numbers_referenced_as_tickets:
        logger.error(f"#{pull_request_reference} is a pull request, not a ticket.")
    if not result.referenced_issue_numbers:
        logger.error("No ticket referenced. Add 'Closes #N' (or 'Part of #N' for a stacked PR) to the description.")
    if not result.is_passing:
        raise SystemExit(1)
    logger.info(f"References {', '.join(f'#{number}' for number in result.referenced_issue_numbers)}.")


@pull_request_review.command("bypass-merge-requirements",
                             help=f"Approve the PR when a repository admin added the '{MERGE_REQUIREMENTS_BYPASS_LABEL}' "
                                  "label; otherwise remove the label and withdraw that approval.")
@click.option("--github-token", envvar="GITHUB_TOKEN", required=True,
              help="Token that can approve pull requests and edit labels. Env: GITHUB_TOKEN")
@click.option("--repository", envvar="GITHUB_REPOSITORY", default="AgentWatchOrg/AgentWatch", show_default=True)
@click.option("--pull-request-number", envvar="PULL_REQUEST_NUMBER", type=int, required=True)
@click.option("--dry-run/--no-dry-run", "is_dry_run", envvar="IS_DRY_RUN", default=False,
              help="Print planned changes without making them. Env: IS_DRY_RUN")
def bypass_merge_requirements_command(github_token: str, repository: str, pull_request_number: int,
                                      is_dry_run: bool) -> None:
    plan: MergeRequirementsBypassPlan = bypass_merge_requirements(
        PullRequestClient(GitHubClient(github_token), repository), pull_request_number, is_dry_run)
    logger.info(format_bypass_decision(plan))
    for change in plan.changes:
        logger.info(f"{change}{' (dry run)' if is_dry_run else ''}")


@pull_request_review.command("check-merge-requirements-bypass",
                             help=f"Exit 0 when a repository admin added the '{MERGE_REQUIREMENTS_BYPASS_LABEL}' "
                                  "label, so required checks can pass without running; exit 1 otherwise.")
@click.option("--github-token", envvar="GITHUB_TOKEN", required=True, help="Env: GITHUB_TOKEN")
@click.option("--repository", envvar="GITHUB_REPOSITORY", default="AgentWatchOrg/AgentWatch", show_default=True)
@click.option("--pull-request-number", envvar="PULL_REQUEST_NUMBER", type=int, required=True)
def check_merge_requirements_bypass_command(github_token: str, repository: str, pull_request_number: int) -> None:
    plan: MergeRequirementsBypassPlan = load_merge_requirements_bypass_plan(
        PullRequestClient(GitHubClient(github_token), repository), pull_request_number)
    logger.info(format_bypass_decision(plan))
    if not plan.is_authorized:
        raise SystemExit(1)


def format_bypass_decision(plan: MergeRequirementsBypassPlan) -> str:
    if plan.is_authorized:
        return f"#{plan.pull_request_number}: bypassed by admin @{plan.labeled_by_login}"
    if plan.labeled_by_login:
        return f"#{plan.pull_request_number}: ignoring label from @{plan.labeled_by_login}, who is not an admin"
    return f"#{plan.pull_request_number}: no admin bypass label"


def format_planned_comment(comment: PlannedReviewComment) -> str:
    return (f"{comment.finding.severity} {comment.finding.category} {comment.placement}: "
            f"{comment.finding.path}:{comment.finding.start_line} {comment.finding.title}")
