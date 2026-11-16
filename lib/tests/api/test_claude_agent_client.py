from pathlib import Path

import pytest
from claude_agent_sdk import ClaudeAgentOptions, Message, SystemMessage
from doubles.claude_agent_test_doubles import ScriptedQuery, build_result_message

from agent_watch.api.claude_agent_client import (
    ClaudeAgentClient, ClaudeAgentConfiguration, ClaudeAgentError, ClaudeAgentResult)


@pytest.fixture
def agent_configuration() -> ClaudeAgentConfiguration:
    return ClaudeAgentConfiguration(model="claude-opus-5-5", maximum_turns=40, working_directory=Path("/checkout"),
                                    system_prompt_appendix="You triage detections.",
                                    output_schema={"type": "object", "properties": {}})


def test_defaults_are_read_only_and_hide_github_credentials(agent_configuration: ClaudeAgentConfiguration) -> None:
    options: ClaudeAgentOptions = ClaudeAgentClient(agent_configuration).build_agent_options()

    assert options.model == "claude-opus-5-5" and options.max_turns == 40
    assert options.setting_sources == ["project"] and options.skills == "all"
    assert options.permission_mode == "dontAsk"
    assert {"Write", "Edit", "WebFetch"} <= set(options.disallowed_tools)
    assert all(tool_rule.startswith(("Read", "Grep", "Glob", "Bash(git ")) for tool_rule in options.allowed_tools)
    assert options.env == {"GITHUB_TOKEN": "", "GH_TOKEN": ""}
    assert options.system_prompt == {"type": "preset", "preset": "claude_code", "append": "You triage detections."}
    assert options.output_format == {"type": "json_schema", "schema": {"type": "object", "properties": {}}}


def test_output_format_is_omitted_without_a_schema() -> None:
    configuration_without_schema: ClaudeAgentConfiguration = ClaudeAgentConfiguration(
        model="model", maximum_turns=5, working_directory=Path("."), system_prompt_appendix="")

    assert ClaudeAgentClient(configuration_without_schema).build_agent_options().output_format is None


def test_run_returns_the_final_result(agent_configuration: ClaudeAgentConfiguration) -> None:
    scripted_query: ScriptedQuery = ScriptedQuery([
        SystemMessage(subtype="init", data={}), build_result_message({"answer": 42}, result="done")])

    result: ClaudeAgentResult = ClaudeAgentClient(agent_configuration, scripted_query).run("Triage alert 7")

    assert result == ClaudeAgentResult(structured_output={"answer": 42}, text="done", turn_count=37,
                                       total_cost_usd=2.25)
    assert scripted_query.received_prompts == ["Triage alert 7"]


@pytest.mark.parametrize("messages", [
    [build_result_message(None, is_error=True, subtype="error_max_turns")],
    [],
], ids=["agent error", "no result message"])
def test_run_raises_when_the_agent_fails(agent_configuration: ClaudeAgentConfiguration,
                                         messages: list[Message]) -> None:
    with pytest.raises(ClaudeAgentError):
        ClaudeAgentClient(agent_configuration, ScriptedQuery(messages)).run("Triage alert 7")
