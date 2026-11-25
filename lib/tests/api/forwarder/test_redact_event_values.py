import json
import time

import pytest
from doubles.forwarder_test_doubles import FAKE_SECRET_VALUES

from agent_watch.api.forwarder.redact_event_values import (
    MAXIMUM_ARGUMENTS_LENGTH, redact_event, redact_text, truncate_arguments)
from agent_watch.api.github_client import JsonObject


MAXIMUM_SECONDS_FOR_A_HOSTILE_ARGUMENT: float = 1.0


@pytest.fixture
def process_exec_event_with_secrets() -> JsonObject:
    return {"schema_version": "1.0", "activity_type": "process_exec",
            "target": "https://fake-user:fake-url-password-0003@127.0.0.1/?t=fake-query-token-0004",
            "details": {"arguments": "-H Authorization: Bearer fake-bearer-token-0001 --password=fake-password-0002 "
                                     "sk-fakeapikey00000000000005", "cwd": "/home/agent"}}


@pytest.fixture
def clean_process_exec_event() -> JsonObject:
    return {"target": "/usr/bin/ls", "details": {"arguments": "-la", "cwd": "/home/agent"}}


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
    ('-H "X-Api-Key: s3cr3tvalue" https://ingest/v1/events', '-H "X-Api-Key: *****" https://ingest/v1/events',
     ["secret-header"]),
    ("-H PRIVATE-TOKEN: glpat-abc123", "-H PRIVATE-TOKEN: *****", ["secret-header"]),
    ("kubectl get secret my-secret -o yaml", "kubectl get secret my-secret -o yaml", []),
    ("cat /etc/app-secret config.yaml", "cat /etc/app-secret config.yaml", []),
    ('curl -d {"api_key":"s3cr3t","password":"hunter2","user":"bob"}',
     'curl -d {"api_key":"*****","password":"*****","user":"bob"}', ["secret-json-field"]),
    ("curl -H Cookie: sessionid=abc123; csrftoken=xyz https://internal/app",
     "curl -H Cookie: ***** https://internal/app", ["cookie-header"]),
    ("-H Set-Cookie: id=a3fWa; Path=/", "-H Set-Cookie: *****", ["cookie-header"]),
    ("echo cookie jar", "echo cookie jar", []),
    ("ls -la /home/agent", "ls -la /home/agent", []),
], ids=["authorization-header", "password-arg", "quoted-token", "url-credential", "url-query", "api-key",
        "flag-containing-secret", "user-credential", "secret-assignment", "more-token-prefixes", "api-key-header",
        "private-token-header",
        "hyphenated-word-before-flag", "hyphenated-path", "json-secret-fields",
        "cookie-header", "set-cookie-header", "cookie-word", "clean"])
def test_redact_text(text: str, expected_text: str, expected_rule_names: list[str]) -> None:
    assert redact_text(text) == (expected_text, expected_rule_names)


@pytest.mark.parametrize("hostile_argument", [
    "a" * 200_000, "token" * 40_000, "-" + "token" * 40_000 + " x", '"' + "token" * 40_000 + '":"x"',
    "token" * 40_000 + "=x", "cookie:" + "a=b;" * 40_000,
], ids=["plain-letters", "repeated-secret-name", "repeated-secret-flag", "repeated-json-key",
        "repeated-assignment", "long-cookie"])
def test_redact_text_finishes_quickly_on_a_hostile_argument(hostile_argument: str) -> None:
    started_at: float = time.perf_counter()

    redact_text(hostile_argument)

    assert time.perf_counter() - started_at < MAXIMUM_SECONDS_FOR_A_HOSTILE_ARGUMENT


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
    assert redacted_event["redaction"] == {"applied": True, "rules": [
        "api-key", "authorization-header", "password-arg", "url-credential", "url-query"]}
    assert redacted_event["details"]["cwd"] == "/home/agent"


def test_redact_event_leaves_a_clean_event_unmarked(clean_process_exec_event: JsonObject) -> None:
    assert redact_event(clean_process_exec_event) == clean_process_exec_event
