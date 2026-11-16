from dataclasses import replace

import pytest
from doubles.pull_request_review_test_doubles import FakePullRequestClient

from agent_watch.api.pull_request_review.check_ticket_reference import (
    check_ticket_reference, find_referenced_issue_numbers)
from agent_watch.api.pull_request_review.models import PullRequest, ReferencedIssue, TicketReferenceCheck


@pytest.mark.parametrize(("pull_request_body", "expected_issue_numbers"), [
    ("Closes #12\n\n**Why:** ...", [12]),
    ("closes #12", [12]),
    ("Fixes #3 and resolves #4", [3, 4]),
    ("Fixed: #5", [5]),
    ("Part of #41\nStack 2/3, on top of #40", [41]),
    ("Closes #7\nCloses #7", [7]),
    ("Related to #9", []),
    ("See issue 12", []),
    ("Closes AgentWatchOrg/Other#12", []),
    ("", []),
], ids=["closes", "lowercase", "fixes and resolves", "colon", "part of in a stack", "duplicate", "unrelated keyword",
        "no hash", "other repository", "empty body"])
def test_find_referenced_issue_numbers(pull_request_body: str, expected_issue_numbers: list[int]) -> None:
    assert find_referenced_issue_numbers(pull_request_body) == expected_issue_numbers


@pytest.mark.parametrize(("pull_request_body", "existing_issues", "is_passing", "expected_missing",
                          "expected_pull_requests"), [
    ("Closes #6", [ReferencedIssue(6, is_pull_request=False)], True, [], []),
    ("Part of #6\nCloses #8", [ReferencedIssue(6, False), ReferencedIssue(8, False)], True, [], []),
    ("No ticket here", [], False, [], []),
    ("Closes #999", [], False, [999], []),
    ("Closes #11", [ReferencedIssue(11, is_pull_request=True)], False, [], [11]),
    ("Closes #6\nCloses #999", [ReferencedIssue(6, False)], False, [999], []),
], ids=["existing issue", "two issues", "no reference", "missing issue", "pull request instead of ticket",
        "one good one missing"])
def test_check_ticket_reference(pull_request: PullRequest, pull_request_body: str,
                                existing_issues: list[ReferencedIssue], is_passing: bool, expected_missing: list[int],
                                expected_pull_requests: list[int]) -> None:
    client: FakePullRequestClient = FakePullRequestClient(replace(pull_request, body=pull_request_body), [],
                                                          existing_issues)

    result: TicketReferenceCheck = check_ticket_reference(client, pull_request.number)

    assert result.is_passing is is_passing
    assert result.missing_issue_numbers == expected_missing
    assert result.pull_request_numbers_referenced_as_tickets == expected_pull_requests
