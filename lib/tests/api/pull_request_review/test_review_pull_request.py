import pytest
from doubles.pull_request_review_test_doubles import (
    ExistingReviewThreadFactory, FakePullRequestClient, FakeReviewAgentClient, ReviewFindingFactory)

from agent_watch.api.pull_request_review.models import (
    REVIEW_SUMMARY_MARKER, ChangedFile, CommentPlacement, ExistingReviewThread, PullRequest, PullRequestReviewPlan,
    PullRequestReviewResult, ReviewAgentRun, ReviewFinding, ReviewFindingCategory, ReviewSeverity)
from agent_watch.api.pull_request_review.pull_request_client import parse_review_thread
from agent_watch.api.pull_request_review.review_pull_request import (
    apply_pull_request_review, build_review_summary, choose_comment_lines, fingerprint_review_finding,
    format_finding_comment_body, is_already_raised, plan_pull_request_review, review_pull_request)


def test_fingerprint_ignores_lines_and_title_punctuation(make_finding: ReviewFindingFactory) -> None:
    original_finding: ReviewFinding = make_finding(start_line=10, title="Off-by-one drops the last page")
    moved_finding: ReviewFinding = make_finding(start_line=42, title="Off-by-one: drops the LAST page!")

    assert fingerprint_review_finding(original_finding) == fingerprint_review_finding(moved_finding)
    assert fingerprint_review_finding(original_finding) != fingerprint_review_finding(
        make_finding(category=ReviewFindingCategory.PERFORMANCE))


@pytest.mark.parametrize(("is_resolved", "is_outdated"), [
    (False, False),
    (True, False),
    (False, True),
], ids=["open", "resolved", "outdated"])
def test_finding_with_a_known_fingerprint_is_already_raised(
        make_finding: ReviewFindingFactory, make_thread: ExistingReviewThreadFactory, is_resolved: bool,
        is_outdated: bool) -> None:
    finding: ReviewFinding = make_finding(start_line=80)
    fingerprint: str = fingerprint_review_finding(finding)
    thread: ExistingReviewThread = make_thread(line=None, finding_fingerprint=fingerprint, is_resolved=is_resolved,
                                               is_outdated=is_outdated)

    assert is_already_raised(finding, fingerprint, [thread])


@pytest.mark.parametrize(("thread_line", "thread_category", "thread_fingerprint", "expected"), [
    (12, ReviewFindingCategory.CORRECTNESS, "0123456789abcdef", True),
    (30, ReviewFindingCategory.CORRECTNESS, "0123456789abcdef", False),
    (12, ReviewFindingCategory.DOCUMENTATION, "0123456789abcdef", False),
    (12, None, None, False),
], ids=["reworded nearby", "far away", "other category", "human comment"])
def test_reworded_finding_near_an_earlier_review_finding_is_already_raised(
        make_finding: ReviewFindingFactory, make_thread: ExistingReviewThreadFactory, thread_line: int,
        thread_category: ReviewFindingCategory | None, thread_fingerprint: str | None, expected: bool) -> None:
    finding: ReviewFinding = make_finding(start_line=10, title="Pagination stops early")
    thread: ExistingReviewThread = make_thread(line=thread_line, finding_category=thread_category,
                                               finding_fingerprint=thread_fingerprint)

    assert is_already_raised(finding, fingerprint_review_finding(finding), [thread]) is expected


@pytest.mark.parametrize(("path", "start_line", "end_line", "expected"), [
    ("lib/src/agent_watch/api/example.py", 9, 11, (CommentPlacement.LINE, 9, 11)),
    ("lib/src/agent_watch/api/example.py", 14, 20, (CommentPlacement.LINE, None, 15)),
    ("lib/src/agent_watch/api/example.py", 50, 52, (CommentPlacement.FILE, None, None)),
    ("README.md", 1, 1, (CommentPlacement.SUMMARY_ONLY, None, None)),
], ids=["inside diff", "partly inside diff", "outside diff", "unchanged file"])
def test_choose_comment_lines(make_finding: ReviewFindingFactory, pull_request: PullRequest, path: str,
                              start_line: int, end_line: int,
                              expected: tuple[CommentPlacement, int | None, int | None]) -> None:
    changed_file: ChangedFile | None = next(
        (changed_file for changed_file in pull_request.changed_files if changed_file.path == path), None)

    assert choose_comment_lines(make_finding(path=path, start_line=start_line, end_line=end_line),
                                changed_file) == expected


def test_comment_body_carries_severity_skill_and_a_parseable_marker(make_finding: ReviewFindingFactory) -> None:
    finding: ReviewFinding = make_finding(category=ReviewFindingCategory.REPOSITORY_GUIDELINES,
                                          violated_skill_name="naming-typing-and-comments")
    body: str = format_finding_comment_body(finding, "0123456789abcdef")

    assert body.startswith("**🟠 High · repository guidelines** · Off-by-one drops the last page")
    assert "`.claude/skills/naming-typing-and-comments/SKILL.md`" in body
    parsed_thread: ExistingReviewThread = parse_review_thread({
        "path": finding.path, "line": 10, "startLine": None, "originalLine": 10, "originalStartLine": None,
        "isResolved": False, "isOutdated": False,
        "comments": {"nodes": [{"body": body, "author": {"login": "github-actions"}}]}})
    assert parsed_thread.finding_fingerprint == "0123456789abcdef"
    assert parsed_thread.finding_category == ReviewFindingCategory.REPOSITORY_GUIDELINES


def test_plan_skips_duplicates_and_orders_by_severity(make_finding: ReviewFindingFactory,
                                                      make_thread: ExistingReviewThreadFactory,
                                                      pull_request: PullRequest) -> None:
    already_raised: ReviewFinding = make_finding(start_line=8, title="Token leaks into logs",
                                                 category=ReviewFindingCategory.SECURITY)
    low_finding: ReviewFinding = make_finding(start_line=9, severity=ReviewSeverity.LOW, title="Typo in docstring",
                                              category=ReviewFindingCategory.DOCUMENTATION)
    critical_finding: ReviewFinding = make_finding(start_line=12, severity=ReviewSeverity.CRITICAL,
                                                   title="Deletes every card")
    thread: ExistingReviewThread = make_thread(line=None, is_resolved=True,
                                               finding_fingerprint=fingerprint_review_finding(already_raised))

    plan: PullRequestReviewPlan = plan_pull_request_review(
        pull_request, [low_finding, already_raised, critical_finding, critical_finding], [thread])

    assert [comment.finding.title for comment in plan.comments] == ["Deletes every card", "Typo in docstring"]
    assert [finding.title for finding in plan.skipped_duplicate_findings] == ["Deletes every card",
                                                                              "Token leaks into logs"]


def test_summary_counts_new_findings_and_lists_unchanged_files(make_finding: ReviewFindingFactory,
                                                               pull_request: PullRequest) -> None:
    plan: PullRequestReviewPlan = plan_pull_request_review(
        pull_request, [make_finding(), make_finding(path="README.md", title="Install step is wrong",
                                                    severity=ReviewSeverity.LOW)], [])

    summary: str = build_review_summary(pull_request, plan, ReviewAgentRun(findings=[], turn_count=23,
                                                                           total_cost_usd=1.5))

    assert summary.startswith(REVIEW_SUMMARY_MARKER)
    assert "Reviewed `head765` in 23 agent turns." in summary
    assert "| 🟠 High | 1 |" in summary and "| ⚪ Low | 1 |" in summary
    assert "`README.md:10` Install step is wrong" in summary


def test_summary_says_when_nothing_is_new(pull_request: PullRequest) -> None:
    summary: str = build_review_summary(pull_request, PullRequestReviewPlan(comments=[], skipped_duplicate_findings=[]),
                                        ReviewAgentRun(findings=[], turn_count=4, total_cost_usd=None))

    assert "No new findings." in summary


def test_apply_posts_line_comments_in_one_review_then_file_comments_then_summary(
        make_finding: ReviewFindingFactory, pull_request: PullRequest) -> None:
    client: FakePullRequestClient = FakePullRequestClient(pull_request, [])
    plan: PullRequestReviewPlan = plan_pull_request_review(pull_request, [
        make_finding(start_line=9, title="Inside the diff"), make_finding(start_line=12, title="Also inside"),
        make_finding(start_line=60, title="Outside the diff")], [])

    apply_pull_request_review(client, pull_request, plan, "summary")

    assert client.recorded_calls == [("post_review", "Inside the diff", "Also inside"),
                                     ("post_file_comment", "Outside the diff"),
                                     ("create_or_update_review_summary", "7")]


@pytest.mark.parametrize(("is_dry_run", "expected_calls"), [
    (True, []),
    (False, [("post_review", "Off-by-one drops the last page"), ("create_or_update_review_summary", "7")]),
], ids=["dry run", "real run"])
def test_review_pull_request_posts_only_outside_dry_run(make_finding: ReviewFindingFactory,
                                                        pull_request: PullRequest, is_dry_run: bool,
                                                        expected_calls: list[tuple[str, ...]]) -> None:
    client: FakePullRequestClient = FakePullRequestClient(pull_request, [])
    agent_client: FakeReviewAgentClient = FakeReviewAgentClient(
        ReviewAgentRun(findings=[make_finding()], turn_count=12, total_cost_usd=None))

    result: PullRequestReviewResult = review_pull_request(client, agent_client, 7, is_dry_run)

    assert client.recorded_calls == expected_calls
    assert result.plan is not None and len(result.plan.comments) == 1


def test_review_pull_request_skips_drafts_without_running_the_agent(pull_request: PullRequest) -> None:
    draft_pull_request: PullRequest = PullRequest(**{**pull_request.__dict__, "is_draft": True})
    client: FakePullRequestClient = FakePullRequestClient(draft_pull_request, [])
    agent_client: FakeReviewAgentClient = FakeReviewAgentClient(
        ReviewAgentRun(findings=[], turn_count=0, total_cost_usd=None))

    result: PullRequestReviewResult = review_pull_request(client, agent_client, 7, is_dry_run=False)

    assert result.agent_run is None and result.plan is None
    assert client.recorded_calls == []
