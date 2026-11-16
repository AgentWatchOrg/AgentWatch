import re
import urllib.error

from agent_watch.api.github_client import GitHubClient, JsonObject
from agent_watch.api.pull_request_review.models import (
    FINDING_MARKER_PATTERN, REVIEW_SUMMARY_MARKER, ChangedFile, ExistingReviewThread, PlannedReviewComment,
    PullRequest, ReferencedIssue, ReviewFindingCategory)

HUNK_HEADER_PATTERN: re.Pattern[str] = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<new_start>\d+)(?:,\d+)? @@")

REVIEW_THREADS_QUERY: str = """query($owner:String!,$name:String!,$number:Int!,$after:String){
  repository(owner:$owner,name:$name){pullRequest(number:$number){reviewThreads(first:100,after:$after){
    pageInfo{hasNextPage endCursor}
    nodes{isResolved isOutdated path line startLine originalLine originalStartLine
      comments(first:1){nodes{body author{login}}}}}}}}"""


class PullRequestClient:
    def __init__(self, github_client: GitHubClient, repository: str) -> None:
        self.github_client: GitHubClient = github_client
        self.repository: str = repository

    def load_pull_request(self, pull_request_number: int) -> PullRequest:
        pull_request: JsonObject = self.github_client.request(
            "GET", f"/repos/{self.repository}/pulls/{pull_request_number}")
        changed_files: list[JsonObject] = self.github_client.request_all_pages(
            f"/repos/{self.repository}/pulls/{pull_request_number}/files")
        return PullRequest(
            number=pull_request["number"],
            title=pull_request["title"],
            body=pull_request["body"] or "",
            author_login=pull_request["user"]["login"],
            base_branch=pull_request["base"]["ref"],
            base_sha=pull_request["base"]["sha"],
            head_sha=pull_request["head"]["sha"],
            is_draft=pull_request["draft"],
            changed_files=[ChangedFile(path=changed_file["filename"],
                                       commentable_line_numbers=parse_commentable_line_numbers(changed_file.get("patch")))
                           for changed_file in changed_files],
        )

    def find_issue(self, issue_number: int) -> ReferencedIssue | None:
        try:
            issue: JsonObject = self.github_client.request("GET", f"/repos/{self.repository}/issues/{issue_number}")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise
        return ReferencedIssue(number=issue["number"], is_pull_request="pull_request" in issue)

    def load_review_threads(self, pull_request_number: int) -> list[ExistingReviewThread]:
        repository_owner: str
        repository_name: str
        repository_owner, repository_name = self.repository.split("/")
        thread_nodes: list[JsonObject] = self.github_client.run_paginated_graphql(
            REVIEW_THREADS_QUERY, ["repository", "pullRequest", "reviewThreads"],
            owner=repository_owner, name=repository_name, number=pull_request_number)
        return [parse_review_thread(node) for node in thread_nodes if node["comments"]["nodes"]]

    def post_review(self, pull_request: PullRequest, line_comments: list[PlannedReviewComment]) -> None:
        self.github_client.request("POST", f"/repos/{self.repository}/pulls/{pull_request.number}/reviews", {
            "commit_id": pull_request.head_sha,
            "event": "COMMENT",
            "comments": [build_line_comment_payload(comment) for comment in line_comments],
        })

    def post_file_comment(self, pull_request: PullRequest, file_comment: PlannedReviewComment) -> None:
        self.github_client.request("POST", f"/repos/{self.repository}/pulls/{pull_request.number}/comments", {
            "commit_id": pull_request.head_sha,
            "path": file_comment.finding.path,
            "subject_type": "file",
            "body": file_comment.body,
        })

    def create_or_update_review_summary(self, pull_request_number: int, summary: str) -> str:
        issue_comments: list[JsonObject] = self.github_client.request_all_pages(
            f"/repos/{self.repository}/issues/{pull_request_number}/comments")
        for issue_comment in issue_comments:
            if REVIEW_SUMMARY_MARKER in (issue_comment["body"] or ""):
                updated_comment: JsonObject = self.github_client.request(
                    "PATCH", f"/repos/{self.repository}/issues/comments/{issue_comment['id']}", {"body": summary})
                updated_comment_url: str = updated_comment["html_url"]
                return updated_comment_url
        created_comment: JsonObject = self.github_client.request(
            "POST", f"/repos/{self.repository}/issues/{pull_request_number}/comments", {"body": summary})
        created_comment_url: str = created_comment["html_url"]
        return created_comment_url


def parse_commentable_line_numbers(patch: str | None) -> frozenset[int]:
    commentable_line_numbers: set[int] = set()
    next_new_line_number: int = 0
    for patch_line in (patch or "").splitlines():
        hunk_header: re.Match[str] | None = HUNK_HEADER_PATTERN.match(patch_line)
        if hunk_header:
            next_new_line_number = int(hunk_header["new_start"])
        elif patch_line.startswith(("+", " ")):
            commentable_line_numbers.add(next_new_line_number)
            next_new_line_number += 1
    return frozenset(commentable_line_numbers)


def parse_review_thread(node: JsonObject) -> ExistingReviewThread:
    first_comment: JsonObject = node["comments"]["nodes"][0]
    finding_marker: re.Match[str] | None = FINDING_MARKER_PATTERN.search(first_comment["body"])
    finding_category: ReviewFindingCategory | None = (
        ReviewFindingCategory(finding_marker["category"])
        if finding_marker and finding_marker["category"] in ReviewFindingCategory.__members__.values() else None)
    return ExistingReviewThread(
        path=node["path"],
        start_line=node["startLine"] or node["originalStartLine"],
        line=node["line"] or node["originalLine"],
        is_resolved=node["isResolved"],
        is_outdated=node["isOutdated"],
        author_login=(first_comment["author"] or {}).get("login", "ghost"),
        body=first_comment["body"],
        finding_fingerprint=finding_marker["fingerprint"] if finding_marker else None,
        finding_category=finding_category,
    )


def build_line_comment_payload(line_comment: PlannedReviewComment) -> JsonObject:
    payload: JsonObject = {"path": line_comment.finding.path, "line": line_comment.line, "side": "RIGHT",
                           "body": line_comment.body}
    if line_comment.start_line is not None and line_comment.start_line != line_comment.line:
        payload |= {"start_line": line_comment.start_line, "start_side": "RIGHT"}
    return payload
