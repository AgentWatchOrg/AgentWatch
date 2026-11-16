import os
from datetime import date, timedelta

from project_board_graphql_client import (
    IS_DRY_RUN, PROJECT_REPOSITORY, SPRINT_LOG_ISSUE_TITLE, TODAY, JsonObject, ProjectBoard, ProjectItem, SprintWeek,
    current_or_next_week, github_request, load_project_board, load_project_items, run_graphql, set_item_week)

SHOULD_POST_SUMMARY: bool = os.environ.get("SHOULD_POST_SUMMARY", "true").lower() == "true"
MINIMUM_FUTURE_WEEKS: int = int(os.environ.get("MINIMUM_FUTURE_WEEKS", "4"))
WEEK_LENGTH_DAYS: int = 7


def add_weeks_if_running_low(board: ProjectBoard) -> list[str]:
    future_week_count: int = sum(1 for week in board.weeks if week.start_date > TODAY)
    if future_week_count >= MINIMUM_FUTURE_WEEKS:
        return []
    weeks_by_start: list[SprintWeek] = sorted(board.weeks, key=lambda week: week.start_date)
    next_start_date: date = weeks_by_start[-1].end_date
    new_weeks: list[JsonObject] = []
    for week_number in range(len(weeks_by_start) + 1, len(weeks_by_start) + 1 + MINIMUM_FUTURE_WEEKS - future_week_count):
        new_weeks.append({"startDate": next_start_date.isoformat(), "duration": WEEK_LENGTH_DAYS,
                          "title": f"Week {week_number} ({next_start_date.strftime('%b')} {next_start_date.day})"})
        next_start_date += timedelta(days=WEEK_LENGTH_DAYS)
    if not IS_DRY_RUN:
        # The API replaces the whole week list; resending existing weeks with their ids keeps cards attached.
        existing_weeks: list[JsonObject] = [
            {"id": week.id, "title": week.title, "startDate": week.start_date.isoformat(), "duration": week.duration_days}
            for week in weeks_by_start]
        run_graphql("""mutation($fieldId:ID!,$configuration:ProjectV2IterationFieldConfigurationInput!){
          updateProjectV2Field(input:{fieldId:$fieldId,iterationConfiguration:$configuration}){
            projectV2Field{... on ProjectV2IterationField{id}}}}""",
                    fieldId=board.week_field_id,
                    configuration={"startDate": existing_weeks[0]["startDate"], "duration": WEEK_LENGTH_DAYS,
                                   "iterations": existing_weeks + new_weeks})
    return [new_week["title"] for new_week in new_weeks]


def repository_collaborator_logins() -> set[str]:
    collaborators: list[JsonObject] = github_request(
        "GET", f"https://api.github.com/repos/{PROJECT_REPOSITORY}/collaborators?per_page=100")
    return {collaborator["login"] for collaborator in collaborators if collaborator["type"] == "User"}


def build_sprint_summary(target_week: SprintWeek, previous_week: SprintWeek | None,
                         finished_items: list[ProjectItem], carried_over_items: list[ProjectItem],
                         this_week_items: list[ProjectItem]) -> str:
    logins_with_work: set[str] = {login for item in this_week_items for login in item.assignee_logins}
    logins_without_work: list[str] = sorted(repository_collaborator_logins() - logins_with_work, key=str.lower)
    summary_lines: list[str] = [f"## {target_week.title} has started", ""]
    if previous_week:
        summary_lines += [f"**Finished in {previous_week.title}** ({len(finished_items)})"]
        summary_lines += [item.summary_line() for item in finished_items] or ["- nothing marked Done"]
        summary_lines += [""]
    summary_lines += [f"**Carried over into {target_week.title}** ({len(carried_over_items)})"]
    summary_lines += [item.summary_line() for item in carried_over_items] or ["- nothing to carry over"]
    summary_lines += ["", "**No cards this week:** " + (
        ", ".join(f"@{login}" for login in logins_without_work) if logins_without_work else "everyone has work 🎉")]
    return "\n".join(summary_lines)


def find_or_create_sprint_log_issue_number() -> int:
    search_results: list[JsonObject] = run_graphql(
        """query($searchQuery:String!){search(type:ISSUE,query:$searchQuery,first:5){nodes{... on Issue{number title}}}}""",
        searchQuery=f'repo:{PROJECT_REPOSITORY} is:issue in:title "{SPRINT_LOG_ISSUE_TITLE}"')["search"]["nodes"]
    for issue in search_results:
        if issue.get("title") == SPRINT_LOG_ISSUE_TITLE:
            existing_issue_number: int = issue["number"]
            return existing_issue_number
    created_issue: JsonObject = github_request("POST", f"https://api.github.com/repos/{PROJECT_REPOSITORY}/issues", {
        "title": SPRINT_LOG_ISSUE_TITLE,
        "body": "Weekly sprint summaries, posted every Monday by `.github/workflows/weekly-sprint-rollover.yml`."})
    created_issue_number: int = created_issue["number"]
    return created_issue_number


def post_sprint_summary(summary: str) -> None:
    if IS_DRY_RUN:
        print("\n--- summary (not posted, dry run) ---\n" + summary)
        return
    sprint_log_issue_number: int = find_or_create_sprint_log_issue_number()
    github_request("POST", f"https://api.github.com/repos/{PROJECT_REPOSITORY}/issues/{sprint_log_issue_number}/comments",
                   {"body": summary})
    print(f"Posted summary on {PROJECT_REPOSITORY}#{sprint_log_issue_number}")


def main() -> None:
    board: ProjectBoard = load_project_board()
    print(f"{board.title}: today is {TODAY}{' (dry run)' if IS_DRY_RUN else ''}")

    target_week: SprintWeek = current_or_next_week(board.weeks)
    earlier_weeks: list[SprintWeek] = sorted((week for week in board.weeks if week.start_date < target_week.start_date),
                                             key=lambda week: week.start_date)
    previous_week: SprintWeek | None = earlier_weeks[-1] if earlier_weeks else None
    print(f"Target week: {target_week.title}")

    project_items: list[ProjectItem] = load_project_items(board.id)
    carried_over_items: list[ProjectItem] = [
        item for item in project_items
        if item.week_start_date and item.week_start_date < target_week.start_date and not item.is_finished]
    for item in carried_over_items:
        print(f"Move {item.summary_line()[2:]}: {item.week_title} -> {target_week.title}")
        if not IS_DRY_RUN:
            set_item_week(board, item.id, target_week)
    print(f"Carried over {len(carried_over_items)} card(s)")

    for added_week_title in add_weeks_if_running_low(board):
        print(f"Added {added_week_title}")

    if SHOULD_POST_SUMMARY:
        finished_items: list[ProjectItem] = [
            item for item in project_items
            if previous_week and item.week_id == previous_week.id and item.is_finished]
        this_week_items: list[ProjectItem] = [
            item for item in project_items if item.week_id == target_week.id] + carried_over_items
        post_sprint_summary(build_sprint_summary(target_week, previous_week, finished_items,
                                                 carried_over_items, this_week_items))


if __name__ == "__main__":
    main()
