import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, Message, ResultMessage, query

from agent_watch.api.github_client import JsonObject

TOOLS_THAT_CHANGE_THINGS: list[str] = ["Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"]
READ_ONLY_REPOSITORY_TOOLS: list[str] = [
    "Read", "Grep", "Glob", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)", "Bash(git blame:*)"]
HIDDEN_GITHUB_CREDENTIALS: dict[str, str] = {"GITHUB_TOKEN": "", "GH_TOKEN": ""}

logger: logging.Logger = logging.getLogger(__name__)

QueryFunction = Callable[..., AsyncIterator[Message]]


class ClaudeAgentError(Exception):
    pass


@dataclass(frozen=True)
class ClaudeAgentConfiguration:
    model: str
    maximum_turns: int
    working_directory: Path
    system_prompt_appendix: str
    output_schema: JsonObject | None = None
    allowed_tools: list[str] = field(default_factory=lambda: list(READ_ONLY_REPOSITORY_TOOLS))
    blocked_tools: list[str] = field(default_factory=lambda: list(TOOLS_THAT_CHANGE_THINGS))
    hidden_environment_variables: dict[str, str] = field(default_factory=lambda: dict(HIDDEN_GITHUB_CREDENTIALS))


@dataclass(frozen=True)
class ClaudeAgentResult:
    structured_output: Any
    text: str | None
    turn_count: int
    total_cost_usd: float | None


class ClaudeAgentClient:
    def __init__(self, configuration: ClaudeAgentConfiguration, run_query: QueryFunction = query) -> None:
        self.configuration: ClaudeAgentConfiguration = configuration
        self.run_query: QueryFunction = run_query

    def build_agent_options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            model=self.configuration.model,
            max_turns=self.configuration.maximum_turns,
            cwd=self.configuration.working_directory,
            setting_sources=["project"],
            skills="all",
            allowed_tools=self.configuration.allowed_tools,
            disallowed_tools=self.configuration.blocked_tools,
            permission_mode="dontAsk",
            system_prompt={"type": "preset", "preset": "claude_code",
                           "append": self.configuration.system_prompt_appendix},
            output_format=({"type": "json_schema", "schema": self.configuration.output_schema}
                           if self.configuration.output_schema else None),
            env=self.configuration.hidden_environment_variables,
        )

    def run(self, prompt: str) -> ClaudeAgentResult:
        result_message: ResultMessage = asyncio.run(self.collect_result_message(prompt))
        if result_message.is_error:
            raise ClaudeAgentError(
                f"Claude agent stopped with an error ({result_message.subtype}, {result_message.terminal_reason}): "
                f"{result_message.errors or result_message.result}")
        logger.info("Claude agent finished in %s turn(s), cost %s USD", result_message.num_turns,
                    result_message.total_cost_usd)
        return ClaudeAgentResult(structured_output=result_message.structured_output, text=result_message.result,
                                 turn_count=result_message.num_turns, total_cost_usd=result_message.total_cost_usd)

    async def collect_result_message(self, prompt: str) -> ResultMessage:
        result_message: ResultMessage | None = None
        async for message in self.run_query(prompt=prompt, options=self.build_agent_options()):
            if isinstance(message, ResultMessage):
                result_message = message
        if result_message is None:
            raise ClaudeAgentError("Claude agent ended without a result message.")
        return result_message
