import hashlib
import re
from collections import Counter

from agent_watch.api.pull_request_review.models import (
    FINDING_MARKER_TEMPLATE, REVIEW_SUMMARY_MARKER, ChangedFile, CommentPlacement, ExistingReviewThread,
    PlannedReviewComment, PullRequest, PullRequestReviewPlan, PullRequestReviewResult, ReviewAgent, ReviewAgentRun,
    ReviewFinding, ReviewSeverity)
from agent_watch.api.pull_request_review.pull_request_client import PullRequestClient

NEARBY_THREAD_LINE_DISTANCE: int = 3
SEVERITY_BADGES: dict[ReviewSeverity, str] = {
    ReviewSeverity.CRITICAL: "🔴 Critical",
    ReviewSeverity.HIGH: "🟠 High",
    ReviewSeverity.MEDIUM: "🟡 Medium",
    ReviewSeverity.LOW: "⚪ Low",
}


def fingerprint_review_finding(finding: ReviewFinding) -> str:
    normalized_title: str = re.sub(r"[^a-z0-9]+", " ", finding.title.lower()).strip()
    return hashlib.sha256(f"{finding.path}|{finding.category}|{normalized_title}".encode()).hexdigest()[:16]


def is_already_raised(finding: ReviewFinding, fingerprint: str, existing_threads: list[ExistingReviewThread]) -> bool:
    for thread in existing_threads:
        if thread.finding_fingerprint == fingerprint:
            return True
        is_same_category_nearby: bool = (
            thread.finding_fingerprint is not None and thread.finding_category == finding.category
            and thread.path == finding.path and thread.line is not None
            and finding.start_line - NEARBY_THREAD_LINE_DISTANCE
            <= thread.line <= finding.end_line + NEARBY_THREAD_LINE_DISTANCE)
        if is_same_category_nearby:
            return True
    return False


def choose_comment_lines(finding: ReviewFinding,
                         changed_file: ChangedFile | None) -> tuple[CommentPlacement, int | None, int | None]:
    if changed_file is None:
        return CommentPlacement.SUMMARY_ONLY, None, None
    finding_lines: range = range(finding.start_line, finding.end_line + 1)
    if all(line_number in changed_file.commentable_line_numbers for line_number in finding_lines):
        return CommentPlacement.LINE, finding.start_line, finding.end_line
    commentable_finding_lines: list[int] = [
        line_number for line_number in finding_lines if line_number in changed_file.commentable_line_numbers]
    if commentable_finding_lines:
        return CommentPlacement.LINE, None, commentable_finding_lines[-1]
    return CommentPlacement.FILE, None, None


def format_finding_comment_body(finding: ReviewFinding, fingerprint: str) -> str:
    heading: str = f"**{SEVERITY_BADGES[finding.severity]} · {finding.category.replace('_', ' ')}** · {finding.title}"
    body_lines: list[str] = [heading, "", finding.explanation, "", f"**Failure scenario:** {finding.failure_scenario}",
                             "", f"**Suggested fix:** {finding.suggested_fix}"]
    if finding.violated_skill_name:
        body_lines += ["", f"**Guideline:** `.claude/skills/{finding.violated_skill_name}/SKILL.md`"]
    body_lines += ["", FINDING_MARKER_TEMPLATE.format(fingerprint=fingerprint, category=finding.category)]
    return "\n".join(body_lines)


def plan_pull_request_review(pull_request: PullRequest, findings: list[ReviewFinding],
                             existing_threads: list[ExistingReviewThread]) -> PullRequestReviewPlan:
    changed_files_by_path: dict[str, ChangedFile] = {
        changed_file.path: changed_file for changed_file in pull_request.changed_files}
    planned_comments: list[PlannedReviewComment] = []
    skipped_duplicate_findings: list[ReviewFinding] = []
    planned_fingerprints: set[str] = set()
    for finding in sorted(findings, key=lambda finding: list(ReviewSeverity).index(finding.severity)):
        fingerprint: str = fingerprint_review_finding(finding)
        if fingerprint in planned_fingerprints or is_already_raised(finding, fingerprint, existing_threads):
            skipped_duplicate_findings.append(finding)
            continue
        placement: CommentPlacement
        start_line: int | None
        line: int | None
        placement, start_line, line = choose_comment_lines(finding, changed_files_by_path.get(finding.path))
        planned_comments.append(PlannedReviewComment(
            finding=finding, fingerprint=fingerprint, placement=placement, start_line=start_line, line=line,
            body=format_finding_comment_body(finding, fingerprint)))
        planned_fingerprints.add(fingerprint)
    return PullRequestReviewPlan(comments=planned_comments, skipped_duplicate_findings=skipped_duplicate_findings)


def build_review_summary(pull_request: PullRequest, plan: PullRequestReviewPlan, agent_run: ReviewAgentRun) -> str:
    severity_counts: Counter[ReviewSeverity] = Counter(comment.finding.severity for comment in plan.comments)
    summary_lines: list[str] = [REVIEW_SUMMARY_MARKER, "## RoboReviewer", "",
                                f"Reviewed `{pull_request.head_sha[:7]}` in {agent_run.turn_count} agent turns."]
    if not plan.comments:
        summary_lines += ["", "No new findings."]
    else:
        summary_lines += ["", "| Severity | New findings |", "|---|---|"]
        summary_lines += [f"| {SEVERITY_BADGES[severity]} | {severity_counts[severity]} |"
                          for severity in ReviewSeverity if severity_counts[severity]]
    if plan.summary_only_comments:
        summary_lines += ["", "### Findings in files this PR does not change"]
        summary_lines += [f"- **{SEVERITY_BADGES[comment.finding.severity]}** `{comment.finding.path}:"
                          f"{comment.finding.start_line}` {comment.finding.title}: {comment.finding.explanation}"
                          for comment in plan.summary_only_comments]
    if plan.skipped_duplicate_findings:
        summary_lines += ["", f"{len(plan.skipped_duplicate_findings)} finding(s) were already raised on this PR "
                              "and were not repeated."]
    return "\n".join(summary_lines)


def apply_pull_request_review(client: PullRequestClient, pull_request: PullRequest, plan: PullRequestReviewPlan,
                              summary: str) -> str:
    if plan.line_comments:
        client.post_review(pull_request, plan.line_comments)
    for file_comment in plan.file_comments:
        client.post_file_comment(pull_request, file_comment)
    return client.create_or_update_review_summary(pull_request.number, summary)


def review_pull_request(pull_request_client: PullRequestClient, review_agent: ReviewAgent,
                        pull_request_number: int, is_dry_run: bool) -> PullRequestReviewResult:
    pull_request: PullRequest = pull_request_client.load_pull_request(pull_request_number)
    if pull_request.is_draft:
        return PullRequestReviewResult(pull_request=pull_request, agent_run=None, plan=None, summary=None,
                                       summary_comment_url=None)
    existing_threads: list[ExistingReviewThread] = pull_request_client.load_review_threads(pull_request_number)
    agent_run: ReviewAgentRun = review_agent.find_review_findings(pull_request, existing_threads)
    plan: PullRequestReviewPlan = plan_pull_request_review(pull_request, agent_run.findings, existing_threads)
    summary: str = build_review_summary(pull_request, plan, agent_run)
    summary_comment_url: str | None = None if is_dry_run else apply_pull_request_review(
        pull_request_client, pull_request, plan, summary)
    return PullRequestReviewResult(pull_request=pull_request, agent_run=agent_run, plan=plan, summary=summary,
                                   summary_comment_url=summary_comment_url)
