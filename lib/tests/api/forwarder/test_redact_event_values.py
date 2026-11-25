import json

import pytest
from doubles.forwarder_test_doubles import FAKE_SECRET_VALUES

from agent_watch.api.forwarder.redact_event_values import (
    MAXIMUM_ARGUMENTS_LENGTH, redact_event, redact_text, truncate_arguments)
from agent_watch.api.github_client import JsonObject


@pytest.fixture
def process_exec_event_with_secrets() -> JsonObject:
    return {"schema_version": "1.0", "activity_type": "process_exec", "target": "/usr/bin/curl", "details": {
        "arguments": "-H Authorization: Bearer fake-bearer-token-0001 --password=fake-password-0002",
        "cwd": "/home/agent"}}


@pytest.mark.parametrize(("text", "expected_text", "expected_rule_names"), [
    ("-H Authorization: Bearer abc123", "-H Authorization: Bearer *****", ["authorization-header"]),
    ("--password=hunter2", "--password=*****", ["password-arg"]),
    ("--token 'two words'", "--token *****", ["password-arg"]),
    ("https://user:pass@host/path", "https://*****@host/path", ["url-credential"]),
    ("https://host/path?token=xyz", "https://host/path?*****", ["url-query"]),
    ("key sk-abcdefghijklmnop1234", "key *****", ["api-key"]),
    ("aws configure set --aws-secret-access-key wJalrXUtn", "aws configure set --aws-secret-access-key *****",
     ["password-arg"]),
    ("curl -u admin:hunter2 https://host", "curl -u admin:***** https://host", ["user-credential"]),
    ("sh -c MYSQL_PWD=s3cr3t mysql", "sh -c MYSQL_PWD=***** mysql", ["secret-assignment"]),
    ("github_pat_11ABCDEFGHIJKLMNOPQRSTUV ghs_ABCDEFGHIJKLMNOPQRSTUVWX xoxb-1234567890-abc", "***** ***** *****",
     ["api-key"]),
    ("kubectl get secret my-secret -o yaml", "kubectl get secret my-secret -o yaml", []),
    ("cat /etc/app-secret config.yaml", "cat /etc/app-secret config.yaml", []),
    ("ls -la /home/agent", "ls -la /home/agent", []),
], ids=["authorization-header", "password-arg", "quoted-token", "url-credential", "url-query", "api-key",
        "flag-containing-secret", "user-credential", "secret-assignment", "more-token-prefixes",
        "hyphenated-word-before-flag", "hyphenated-path", "clean"])
def test_redact_text(text: str, expected_text: str, expected_rule_names: list[str]) -> None:
    assert redact_text(text) == (expected_text, expected_rule_names)


def test_redact_text_scans_a_long_argument_in_linear_time() -> None:
    long_argument: str = "a" * 200_000

    assert redact_text(long_argument) == (long_argument, [])


def test_truncate_arguments_keeps_short_arguments() -> None:
    assert truncate_arguments("short") == ("short", [])


def test_truncate_arguments_cuts_long_arguments_at_the_limit() -> None:
    truncated_arguments, rule_names = truncate_arguments("a" * (MAXIMUM_ARGUMENTS_LENGTH + 10))

    assert len(truncated_arguments) == MAXIMUM_ARGUMENTS_LENGTH
    assert rule_names == ["argument-truncation"]


def test_redact_event_removes_secrets_and_records_the_rules(process_exec_event_with_secrets: JsonObject) -> None:
    redacted_event: JsonObject = redact_event(process_exec_event_with_secrets)

    serialized_event: str = json.dumps(redacted_event)
    assert all(secret_value not in serialized_event for secret_value in FAKE_SECRET_VALUES)
    assert redacted_event["redaction"] == {"applied": True, "rules": ["authorization-header", "password-arg"]}
    assert redacted_event["details"]["cwd"] == "/home/agent"


def test_redact_event_leaves_a_clean_event_unmarked() -> None:
    clean_event: JsonObject = {"target": "/usr/bin/ls", "details": {"arguments": "-la", "cwd": "/home/agent"}}

    assert redact_event(clean_event) == clean_event
