from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, Message, ResultMessage


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


def build_result_message(structured_output: Any, is_error: bool = False, subtype: str = "success",
                         result: str | None = None) -> ResultMessage:
    return ResultMessage(subtype=subtype, duration_ms=1, duration_api_ms=1, is_error=is_error, num_turns=37,
                         session_id="session", total_cost_usd=2.25, structured_output=structured_output, result=result)
