import re
from dataclasses import dataclass
from enum import StrEnum

MAXIMUM_AGENT_TURNS: int = 150
DEFAULT_REVIEW_MODEL: str = "us.anthropic.claude-opus-5-5"
REVIEW_SUMMARY_MARKER: str = "<!-- agent-watch-pull-request-review-summary -->"
FINDING_MARKER_TEMPLATE: str = "<!-- agent-watch-review-finding fingerprint={fingerprint} category={category} -->"
FINDING_MARKER_PATTERN: re.Pattern[str] = re.compile(
    r"<!-- agent-watch-review-finding fingerprint=(?P<fingerprint>[0-9a-f]+) category=(?P<category>[a-z_]+) -->")


class PullRequestReviewError(Exception):
    pass


class ReviewSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewFindingCategory(StrEnum):
    CORRECTNESS = "correctness"
    SECURITY = "security"
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    TESTING = "testing"
    REPOSITORY_GUIDELINES = "repository_guidelines"
    MAINTAINABILITY = "maintainability"
    DOCUMENTATION = "documentation"
    OTHER = "other"


class CommentPlacement(StrEnum):
    LINE = "line"
    FILE = "file"
    SUMMARY_ONLY = "summary only"


@dataclass(frozen=True)
class ReviewFinding:
    path: str
    start_line: int
    end_line: int
    severity: ReviewSeverity
    category: ReviewFindingCategory
    title: str
    explanation: str
    failure_scenario: str
    suggested_fix: str
    violated_skill_name: str | None = None


@dataclass(frozen=True)
class ChangedFile:
    path: str
    commentable_line_numbers: frozenset[int]


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    body: str
    author_login: str
    base_branch: str
    base_sha: str
    head_sha: str
    is_draft: bool
    changed_files: list[ChangedFile]


@dataclass(frozen=True)
class ExistingReviewThread:
    path: str
    start_line: int | None
    line: int | None
    is_resolved: bool
    is_outdated: bool
    author_login: str
    body: str
    finding_fingerprint: str | None
    finding_category: ReviewFindingCategory | None


@dataclass(frozen=True)
class PlannedReviewComment:
    finding: ReviewFinding
    fingerprint: str
    placement: CommentPlacement
    start_line: int | None
    line: int | None
    body: str


@dataclass(frozen=True)
class PullRequestReviewPlan:
    comments: list[PlannedReviewComment]
    skipped_duplicate_findings: list[ReviewFinding]

    @property
    def line_comments(self) -> list[PlannedReviewComment]:
        return [comment for comment in self.comments if comment.placement == CommentPlacement.LINE]

    @property
    def file_comments(self) -> list[PlannedReviewComment]:
        return [comment for comment in self.comments if comment.placement == CommentPlacement.FILE]

    @property
    def summary_only_comments(self) -> list[PlannedReviewComment]:
        return [comment for comment in self.comments if comment.placement == CommentPlacement.SUMMARY_ONLY]


@dataclass(frozen=True)
class ReviewAgentRun:
    findings: list[ReviewFinding]
    turn_count: int
    total_cost_usd: float | None


@dataclass(frozen=True)
class PullRequestReviewResult:
    pull_request: PullRequest
    agent_run: ReviewAgentRun | None
    plan: PullRequestReviewPlan | None
    summary: str | None
    summary_comment_url: str | None
