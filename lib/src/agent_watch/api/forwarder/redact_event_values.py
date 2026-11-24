import re
from dataclasses import dataclass
from typing import Any

from agent_watch.api.github_client import JsonObject

REDACTED_VALUE: str = "*****"
MAXIMUM_ARGUMENTS_LENGTH: int = 1024
ARGUMENT_TRUNCATION_RULE_NAME: str = "argument-truncation"


@dataclass(frozen=True)
class RedactionRule:
    name: str
    pattern: re.Pattern[str]
    replacement: str


REDACTION_RULES: list[RedactionRule] = [
    RedactionRule("authorization-header", re.compile(
        r"(?i)(authorization:\s*(?:(?:bearer|basic|token)\s+)?)[^\s\"']+"), rf"\g<1>{REDACTED_VALUE}"),
    RedactionRule("password-arg", re.compile(
        r"(?i)(--?(?:password|passwd|pwd|secret|token|api[-_]?key)(?:=|\s+))(\"[^\"]*\"|'[^']*'|\S+)"),
        rf"\g<1>{REDACTED_VALUE}"),
    RedactionRule("url-credential", re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/@]+@"), rf"\g<1>{REDACTED_VALUE}@"),
    RedactionRule("url-query", re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^\s?#\"']*)\?[^\s#\"']+"),
                  rf"\g<1>?{REDACTED_VALUE}"),
    RedactionRule("api-key", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"),
                  REDACTED_VALUE),
]


def redact_text(text: str) -> tuple[str, list[str]]:
    applied_rule_names: list[str] = []
    for rule in REDACTION_RULES:
        text, replacement_count = rule.pattern.subn(rule.replacement, text)
        if replacement_count:
            applied_rule_names.append(rule.name)
    return text, applied_rule_names


def truncate_arguments(arguments: str) -> tuple[str, list[str]]:
    if len(arguments) <= MAXIMUM_ARGUMENTS_LENGTH:
        return arguments, []
    return arguments[:MAXIMUM_ARGUMENTS_LENGTH], [ARGUMENT_TRUNCATION_RULE_NAME]


def redact_event(event: JsonObject) -> JsonObject:
    applied_rule_names: list[str] = []
    redacted_details: JsonObject = {}
    for field_name, field_value in event["details"].items():
        redacted_value: Any = field_value
        if isinstance(field_value, str):
            redacted_value, rule_names = redact_text(field_value)
            applied_rule_names += rule_names
        if field_name == "arguments" and isinstance(redacted_value, str):
            redacted_value, rule_names = truncate_arguments(redacted_value)
            applied_rule_names += rule_names
        redacted_details[field_name] = redacted_value
    redacted_target, target_rule_names = redact_text(event["target"])
    applied_rule_names += target_rule_names

    redacted_event: JsonObject = {**event, "target": redacted_target, "details": redacted_details}
    if applied_rule_names:
        redacted_event["redaction"] = {"applied": True, "rules": sorted(set(applied_rule_names))}
    return redacted_event
