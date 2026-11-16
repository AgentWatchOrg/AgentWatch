import pytest
from click.testing import CliRunner, Result
from doubles.pull_request_review_test_doubles import ReviewFindingFactory

from agent_watch.api.pull_request_review.models import (
    PullRequest, PullRequestReviewPlan, PullRequestReviewResult, ReviewAgentRun)
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
