from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions, Message, ResultMessage, SystemMessage
from doubles.pull_request_review_test_doubles import ExistingReviewThreadFactory

from agent_watch.api.pull_request_review.models import (
    MAXIMUM_AGENT_TURNS, PullRequest, PullRequestReviewError, ReviewAgentRun, ReviewFindingCategory, ReviewSeverity)
from agent_watch.api.pull_request_review.review_agent_client import (
    REVIEWER_SKILL_NAME, ClaudeReviewAgentClient, build_review_prompt, parse_review_findings)


class ScriptedQuery:
    def __init__(self, messages: list[Message]) -> None:
        self.messages: list[Message] = messages
        self.received_prompts: list[str] = []
        self.received_options: list[ClaudeAgentOptions] = []

    async def __call__(self, *, prompt: str, options: ClaudeAgentOptions) -> AsyncIterator[Message]:
        self.received_prompts.append(prompt)
        self.received_options.append(options)
        for message in self.messages:
            yield message


@pytest.fixture
def finding_output() -> dict[str, Any]:
    return {"findings": [{
        "path": "lib/a.py", "start_line": 14, "end_line": 12, "severity": "critical", "category": "security",
        "title": "Token printed", "explanation": "The token is echoed.", "failure_scenario": "Logs leak it.",
        "suggested_fix": "Mask it.", "violated_skill_name": ""}]}


def build_result_message(structured_output: Any, is_error: bool = False, subtype: str = "success") -> ResultMessage:
    return ResultMessage(subtype=subtype, duration_ms=1, duration_api_ms=1, is_error=is_error, num_turns=37,
                         session_id="session", total_cost_usd=2.25, structured_output=structured_output)


def test_agent_options_cap_turns_load_project_skills_and_stay_read_only() -> None:
    options: ClaudeAgentOptions = ClaudeReviewAgentClient(
        "us.anthropic.claude-opus-5-5", MAXIMUM_AGENT_TURNS, Path("/checkout")).build_agent_options()

    assert options.max_turns == 150
    assert options.setting_sources == ["project"] and options.skills == "all"
    assert options.permission_mode == "dontAsk"
    assert {"Write", "Edit", "WebFetch"} <= set(options.disallowed_tools)
    assert all(tool_rule.startswith(("Read", "Grep", "Glob", "Bash(git ")) for tool_rule in options.allowed_tools)
    assert options.output_format is not None and options.output_format["type"] == "json_schema"
    assert options.env["GITHUB_TOKEN"] == "" and options.env["GH_TOKEN"] == ""


def test_find_review_findings_returns_the_structured_output(pull_request: PullRequest,
                                                            finding_output: dict[str, Any]) -> None:
    scripted_query: ScriptedQuery = ScriptedQuery([
        SystemMessage(subtype="init", data={}), build_result_message(finding_output)])

    agent_run: ReviewAgentRun = ClaudeReviewAgentClient(
        "model", 150, Path("."), run_query=scripted_query).find_review_findings(pull_request, [])

    assert agent_run.turn_count == 37 and agent_run.total_cost_usd == 2.25
    assert agent_run.findings[0].severity == ReviewSeverity.CRITICAL
    assert "#7" in scripted_query.received_prompts[0]


@pytest.mark.parametrize("messages", [
    [build_result_message(None, is_error=True, subtype="error_max_turns")],
    [build_result_message(None)],
    [],
], ids=["turn limit", "no structured output", "no result message"])
def test_find_review_findings_raises_when_the_agent_gives_no_findings(pull_request: PullRequest,
                                                                      messages: list[Message]) -> None:
    client: ClaudeReviewAgentClient = ClaudeReviewAgentClient("model", 150, Path("."),
                                                              run_query=ScriptedQuery(messages))

    with pytest.raises(PullRequestReviewError):
        client.find_review_findings(pull_request, [])


def test_prompt_lists_changed_files_and_every_existing_comment(pull_request: PullRequest,
                                                               make_thread: ExistingReviewThreadFactory) -> None:
    prompt: str = build_review_prompt(pull_request, [make_thread(is_resolved=True, author_login="graziamena")])

    assert "git diff base1234567...head7654321" in prompt
    assert "- `lib/src/agent_watch/api/example.py`" in prompt
    assert "(resolved, @graziamena): Earlier comment" in prompt
    assert REVIEWER_SKILL_NAME not in prompt


def test_parse_review_findings_orders_lines_and_blanks_skill(finding_output: dict[str, Any]) -> None:
    finding = parse_review_findings(finding_output)[0]

    assert (finding.start_line, finding.end_line) == (12, 14)
    assert finding.category == ReviewFindingCategory.SECURITY
    assert finding.violated_skill_name is None
