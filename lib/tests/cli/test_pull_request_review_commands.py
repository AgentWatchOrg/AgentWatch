import subprocess
import sys

import pytest
from click.testing import CliRunner, Result
from doubles.pull_request_review_test_doubles import ReviewFindingFactory

from agent_watch.api.pull_request_review.models import (
    PullRequest, PullRequestReviewPlan, PullRequestReviewResult, ReviewAgentRun, TicketReferenceCheck)
from agent_watch.api.pull_request_review.pull_request_client import PullRequestClient
from agent_watch.api.pull_request_review.review_agent_client import ClaudeReviewAgentClient
from agent_watch.api.pull_request_review.review_pull_request import plan_pull_request_review
from agent_watch.cli import pull_request_review_commands
from agent_watch.cli.main import agent_watch


def test_review_requires_a_pull_request_number(cli_runner: CliRunner) -> None:
    result: Result = cli_runner.invoke(agent_watch, ["pull-request-review", "review"],
                                        env={"GITHUB_TOKEN": "token", "PULL_REQUEST_NUMBER": None})

    assert result.exit_code != 0
    assert "--pull-request-number" in result.output


def test_review_prints_planned_comments_and_totals(cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch,
                                                   pull_request: PullRequest,
                                                   make_finding: ReviewFindingFactory) -> None:
    plan: PullRequestReviewPlan = plan_pull_request_review(pull_request, [make_finding()], [])
    received_arguments: list[tuple[int, bool, str, int]] = []

    def fake_review_pull_request(pull_request_client: PullRequestClient,
                                 review_agent_client: ClaudeReviewAgentClient, pull_request_number: int,
                                 is_dry_run: bool) -> PullRequestReviewResult:
        received_arguments.append((pull_request_number, is_dry_run, review_agent_client.model,
                                   review_agent_client.maximum_agent_turns))
        return PullRequestReviewResult(
            pull_request=pull_request, agent_run=ReviewAgentRun(findings=[], turn_count=40, total_cost_usd=None),
            plan=plan, summary="summary", summary_comment_url=None)

    monkeypatch.setattr(pull_request_review_commands, "review_pull_request", fake_review_pull_request)

    result: Result = cli_runner.invoke(agent_watch, ["pull-request-review", "review"], env={
        "GITHUB_TOKEN": "token", "PULL_REQUEST_NUMBER": "7", "IS_DRY_RUN": "true",
        "PULL_REQUEST_REVIEWER_MODEL": "claude-opus-5-5"})

    assert result.exit_code == 0, result.output
    assert received_arguments == [(7, True, "claude-opus-5-5", 150)]
    assert "high correctness line: lib/src/agent_watch/api/example.py:10 Off-by-one" in result.output
    assert "1 new finding(s), 0 already raised, 40 agent turn(s) (dry run)" in result.output


def test_review_reports_skipped_drafts(cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch,
                                       pull_request: PullRequest) -> None:
    def fake_review_pull_request(pull_request_client: PullRequestClient,
                                 review_agent_client: ClaudeReviewAgentClient, pull_request_number: int,
                                 is_dry_run: bool) -> PullRequestReviewResult:
        return PullRequestReviewResult(pull_request=pull_request, agent_run=None, plan=None, summary=None,
                                       summary_comment_url=None)

    monkeypatch.setattr(pull_request_review_commands, "review_pull_request", fake_review_pull_request)

    result: Result = cli_runner.invoke(agent_watch, ["pull-request-review", "review"],
                                        env={"GITHUB_TOKEN": "token", "PULL_REQUEST_NUMBER": "7"})

    assert result.exit_code == 0, result.output
    assert "Skipped AgentWatchOrg/AgentWatch#7: draft pull request" in result.output


@pytest.mark.parametrize(("check_result", "expected_exit_code", "expected_message"), [
    (TicketReferenceCheck(30, [12, 14], [], []), 0, "References #12, #14."),
    (TicketReferenceCheck(30, [], [], []), 1, "No ticket referenced."),
    (TicketReferenceCheck(30, [999], [999], []), 1, "#999 does not exist in AgentWatchOrg/AgentWatch."),
    (TicketReferenceCheck(30, [11], [], [11]), 1, "#11 is a pull request, not a ticket."),
], ids=["passing", "no reference", "missing issue", "pull request reference"])
def test_check_ticket_reference_reports_and_sets_the_exit_code(
        cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, check_result: TicketReferenceCheck,
        expected_exit_code: int, expected_message: str) -> None:
    def fake_check_ticket_reference(client: PullRequestClient, pull_request_number: int) -> TicketReferenceCheck:
        return check_result

    monkeypatch.setattr(pull_request_review_commands, "check_ticket_reference", fake_check_ticket_reference)

    result: Result = cli_runner.invoke(
        agent_watch, ["pull-request-review", "check-ticket-reference"],
        env={"GITHUB_TOKEN": "token", "GITHUB_REPOSITORY": "AgentWatchOrg/AgentWatch", "PULL_REQUEST_NUMBER": "30"})

    assert result.exit_code == expected_exit_code
    assert expected_message in result.output



def test_cli_loads_without_importing_the_claude_agent_sdk() -> None:
    import_check: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", "import sys, agent_watch.cli.main; print('claude_agent_sdk' in sys.modules)"],
        capture_output=True, text=True, check=True)

    assert import_check.stdout.strip() == "False"


def test_review_explains_how_to_install_the_sdk_when_it_is_missing(cli_runner: CliRunner,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)
    monkeypatch.delitem(sys.modules, "agent_watch.api.pull_request_review.review_agent_client", raising=False)

    result: Result = cli_runner.invoke(agent_watch, ["pull-request-review", "review"],
                                       env={"GITHUB_TOKEN": "token", "PULL_REQUEST_NUMBER": "30"})

    assert result.exit_code == 1
    assert "pip install 'agent-watch[claude-agent]'" in result.output
