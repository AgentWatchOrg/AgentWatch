import urllib.error
from email.message import Message

import pytest
from doubles.github_test_doubles import ScriptedGitHubClient
from doubles.pull_request_review_test_doubles import ReviewFindingFactory

from agent_watch.api.github_client import JsonObject
from agent_watch.api.pull_request_review.models import (
    REVIEW_SUMMARY_MARKER, CommentPlacement, ExistingReviewThread, PlannedReviewComment, PullRequest, ReferencedIssue)
from agent_watch.api.pull_request_review.pull_request_client import (
    PullRequestClient, build_line_comment_payload, parse_commentable_line_numbers, parse_review_thread)

TWO_HUNK_PATCH: str = "\n".join([
    "@@ -1,3 +1,4 @@", " import json", "-import os", "+import pathlib", "+import sys", " ",
    "@@ -20,2 +21,3 @@ def load():", "     return 1", "+    return 2", "\\ No newline at end of file"])


@pytest.fixture
def review_thread_node() -> JsonObject:
    return {"path": "lib/a.py", "line": None, "startLine": None, "originalLine": 14, "originalStartLine": 12,
            "isResolved": True, "isOutdated": True,
            "comments": {"nodes": [{"body": "Please rename this", "author": None}]}}


@pytest.mark.parametrize(("patch", "expected_line_numbers"), [
    (TWO_HUNK_PATCH, {1, 2, 3, 4, 21, 22}),
    (None, set()),
], ids=["two hunks", "binary file"])
def test_parse_commentable_line_numbers(patch: str | None, expected_line_numbers: set[int]) -> None:
    assert parse_commentable_line_numbers(patch) == expected_line_numbers


def test_load_pull_request_reads_files_across_pages(github_client: ScriptedGitHubClient,
                                                    pull_request_client: PullRequestClient) -> None:
    github_client.rest_responses = [
        {"number": 7, "title": "Add retry", "body": None, "user": {"login": "joliejony"}, "draft": False,
         "base": {"ref": "main", "sha": "base-sha"}, "head": {"sha": "head-sha"}},
        [{"filename": f"file_{index}.py", "patch": "@@ -0,0 +1 @@\n+x"} for index in range(100)],
        [{"filename": "image.png"}],
    ]

    pull_request: PullRequest = pull_request_client.load_pull_request(7)

    assert pull_request.body == "" and pull_request.head_sha == "head-sha"
    assert len(pull_request.changed_files) == 101
    assert pull_request.changed_files[0].commentable_line_numbers == {1}
    assert pull_request.changed_files[100].commentable_line_numbers == frozenset()
    assert github_client.rest_calls[2][1] == "/repos/AgentWatchOrg/AgentWatch/pulls/7/files?per_page=100&page=2"


def test_parse_review_thread_falls_back_to_original_lines_for_outdated_threads(review_thread_node: JsonObject) -> None:
    thread: ExistingReviewThread = parse_review_thread(review_thread_node)

    assert (thread.start_line, thread.line) == (12, 14)
    assert thread.author_login == "ghost"
    assert thread.finding_fingerprint is None and thread.finding_category is None


def test_load_review_threads_skips_threads_without_comments(github_client: ScriptedGitHubClient,
                                                            pull_request_client: PullRequestClient,
                                                            review_thread_node: JsonObject) -> None:
    github_client.graphql_responses = [{"repository": {"pullRequest": {"reviewThreads": {
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "nodes": [review_thread_node, {**review_thread_node, "comments": {"nodes": []}}]}}}}]

    threads: list[ExistingReviewThread] = pull_request_client.load_review_threads(7)

    assert len(threads) == 1
    assert github_client.graphql_calls[0][1]["number"] == 7


@pytest.mark.parametrize(("start_line", "line", "expected_range_keys"), [
    (9, 11, {"start_line": 9, "start_side": "RIGHT"}),
    (None, 11, {}),
], ids=["multi line", "single line"])
def test_build_line_comment_payload(make_finding: ReviewFindingFactory, start_line: int | None, line: int,
                                    expected_range_keys: JsonObject) -> None:
    comment: PlannedReviewComment = PlannedReviewComment(
        finding=make_finding(), fingerprint="abc", placement=CommentPlacement.LINE, start_line=start_line, line=line,
        body="body")

    assert build_line_comment_payload(comment) == {
        "path": "lib/src/agent_watch/api/example.py", "line": line, "side": "RIGHT", "body": "body",
        **expected_range_keys}


def test_post_review_and_file_comment_target_the_head_commit(
        github_client: ScriptedGitHubClient, pull_request_client: PullRequestClient, pull_request: PullRequest,
        make_finding: ReviewFindingFactory) -> None:
    comment: PlannedReviewComment = PlannedReviewComment(
        finding=make_finding(), fingerprint="abc", placement=CommentPlacement.FILE, start_line=None, line=None,
        body="body")

    pull_request_client.post_review(pull_request, [comment])
    pull_request_client.post_file_comment(pull_request, comment)

    review_body: JsonObject | None = github_client.rest_calls[0][2]
    file_comment_body: JsonObject | None = github_client.rest_calls[1][2]
    assert review_body is not None and review_body["event"] == "COMMENT"
    assert review_body["commit_id"] == "head7654321"
    assert file_comment_body is not None and file_comment_body["subject_type"] == "file"


@pytest.mark.parametrize(("issue_comments", "expected_method", "expected_path"), [
    ([{"id": 5, "body": "Thanks!"}, {"id": 6, "body": f"{REVIEW_SUMMARY_MARKER}\nold"}],
     "PATCH", "/repos/AgentWatchOrg/AgentWatch/issues/comments/6"),
    ([{"id": 5, "body": None}], "POST", "/repos/AgentWatchOrg/AgentWatch/issues/7/comments"),
], ids=["edits existing summary", "creates first summary"])
def test_create_or_update_review_summary(github_client: ScriptedGitHubClient, pull_request_client: PullRequestClient,
                                         issue_comments: list[JsonObject], expected_method: str,
                                         expected_path: str) -> None:
    github_client.rest_responses = [issue_comments, {"html_url": "https://github.com/comment"}]

    comment_url: str = pull_request_client.create_or_update_review_summary(7, "new summary")

    assert comment_url == "https://github.com/comment"
    assert github_client.rest_calls[1] == (expected_method, expected_path, {"body": "new summary"})


@pytest.mark.parametrize(("issue_response", "expected_issue"), [
    ({"number": 12}, ReferencedIssue(number=12, is_pull_request=False)),
    ({"number": 12, "pull_request": {"url": "https://api.github.com/..."}}, ReferencedIssue(number=12, is_pull_request=True)),
    (urllib.error.HTTPError("https://api.github.com", 404, "Not Found", Message(), None), None),
], ids=["issue", "pull request", "missing"])
def test_find_issue(github_client: ScriptedGitHubClient, pull_request_client: PullRequestClient,
                    issue_response: object, expected_issue: ReferencedIssue | None) -> None:
    github_client.rest_responses = [issue_response]

    assert pull_request_client.find_issue(12) == expected_issue
    assert github_client.rest_calls == [("GET", "/repos/AgentWatchOrg/AgentWatch/issues/12", None)]


def test_find_issue_raises_on_other_http_errors(github_client: ScriptedGitHubClient,
                                                pull_request_client: PullRequestClient) -> None:
    github_client.rest_responses = [urllib.error.HTTPError("https://api.github.com", 500, "Error", Message(), None)]

    with pytest.raises(urllib.error.HTTPError):
        pull_request_client.find_issue(12)

