from typing import Protocol

from doubles.github_test_doubles import ScriptedGitHubClient

from agent_watch.api.pull_request_review.models import (
    ExistingReviewThread, PlannedReviewComment, PullRequest, ReferencedIssue, ReviewAgentRun, ReviewFinding,
    ReviewFindingCategory, ReviewSeverity)
from agent_watch.api.pull_request_review.pull_request_client import PullRequestClient


class ReviewFindingFactory(Protocol):
    def __call__(self, path: str = "lib/src/agent_watch/api/example.py", start_line: int = 10,
                 end_line: int | None = None, severity: ReviewSeverity = ReviewSeverity.HIGH,
                 category: ReviewFindingCategory = ReviewFindingCategory.CORRECTNESS,
                 title: str = "Off-by-one drops the last page",
                 violated_skill_name: str | None = None) -> ReviewFinding: ...


class ExistingReviewThreadFactory(Protocol):
    def __call__(self, path: str = "lib/src/agent_watch/api/example.py", line: int | None = 10,
                 finding_fingerprint: str | None = None,
                 finding_category: ReviewFindingCategory | None = None, is_resolved: bool = False,
                 is_outdated: bool = False, author_login: str = "github-actions") -> ExistingReviewThread: ...


class FakePullRequestClient(PullRequestClient):
    def __init__(self, pull_request: PullRequest, existing_threads: list[ExistingReviewThread],
                 referenced_issues: list[ReferencedIssue] | None = None) -> None:
        super().__init__(ScriptedGitHubClient(), "AgentWatchOrg/AgentWatch")
        self.pull_request: PullRequest = pull_request
        self.existing_threads: list[ExistingReviewThread] = existing_threads
        self.referenced_issues_by_number: dict[int, ReferencedIssue] = {
            issue.number: issue for issue in referenced_issues or []}
        self.recorded_calls: list[tuple[str, ...]] = []

    def load_pull_request(self, pull_request_number: int) -> PullRequest:
        return self.pull_request

    def find_issue(self, issue_number: int) -> ReferencedIssue | None:
        return self.referenced_issues_by_number.get(issue_number)

    def load_review_threads(self, pull_request_number: int) -> list[ExistingReviewThread]:
        return self.existing_threads

    def post_review(self, pull_request: PullRequest, line_comments: list[PlannedReviewComment]) -> None:
        self.recorded_calls.append(("post_review", *[comment.finding.title for comment in line_comments]))

    def post_file_comment(self, pull_request: PullRequest, file_comment: PlannedReviewComment) -> None:
        self.recorded_calls.append(("post_file_comment", file_comment.finding.title))

    def create_or_update_review_summary(self, pull_request_number: int, summary: str) -> str:
        self.recorded_calls.append(("create_or_update_review_summary", str(pull_request_number)))
        return "https://github.com/AgentWatchOrg/AgentWatch/pull/7#issuecomment-1"


class FakeReviewAgent:
    def __init__(self, agent_run: ReviewAgentRun) -> None:
        self.agent_run: ReviewAgentRun = agent_run
        self.received_existing_threads: list[ExistingReviewThread] = []

    def find_review_findings(self, pull_request: PullRequest,
                             existing_threads: list[ExistingReviewThread]) -> ReviewAgentRun:
        self.received_existing_threads = existing_threads
        return self.agent_run
