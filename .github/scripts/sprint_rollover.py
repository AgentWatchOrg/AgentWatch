import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

JsonObject = dict[str, Any]

GITHUB_TOKEN: str = os.environ["GH_TOKEN"]
PROJECT_OWNER: str = os.environ.get("OWNER", "AgentWatchOrg")
PROJECT_NUMBER: int = int(os.environ.get("PROJECT_NUMBER", "1"))
SPRINT_LOG_REPOSITORY: str = os.environ.get("REPO", "AgentWatchOrg/AgentWatch")
IS_DRY_RUN: bool = os.environ.get("DRY_RUN", "false").lower() == "true"
SHOULD_POST_SUMMARY: bool = os.environ.get("POST_SUMMARY", "true").lower() == "true"
MINIMUM_FUTURE_WEEKS: int = int(os.environ.get("MIN_FUTURE_WEEKS", "4"))
TODAY: date = (date.fromisoformat(os.environ["TODAY"]) if os.environ.get("TODAY")
               else datetime.now(ZoneInfo("America/Edmonton")).date())

WEEK_FIELD_NAME: str = "Week"
DONE_STATUS: str = "Done"
CLOSED_CONTENT_STATES: frozenset[str] = frozenset({"CLOSED", "MERGED"})
SPRINT_LOG_ISSUE_TITLE: str = "Sprint Log"
WEEK_LENGTH_DAYS: int = 7


@dataclass(frozen=True)
class SprintWeek:
    id: str
    title: str
    start_date: date
    duration_days: int

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=self.duration_days)

    def contains(self, day: date) -> bool:
        return self.start_date <= day < self.end_date


@dataclass(frozen=True)
class WeekField:
    id: str
    weeks: list[SprintWeek]


@dataclass(frozen=True)
class ProjectItem:
    id: str
    title: str
    status: str | None
    week_id: str | None
    week_title: str | None
    week_start_date: date | None
    issue_number: int | None
    issue_url: str | None
    issue_state: str | None
    assignee_logins: list[str]

    @property
    def is_finished(self) -> bool:
        return self.status == DONE_STATUS or self.issue_state in CLOSED_CONTENT_STATES

    def summary_line(self) -> str:
        assignees: str = ", ".join(f"@{login}" for login in self.assignee_logins) or "_unassigned_"
        reference: str = f"[#{self.issue_number}]({self.issue_url})" if self.issue_number else "(draft)"
        return f"- {reference} {self.title} ({assignees})"


def github_request(method: str, url: str, body: JsonObject | None = None) -> Any:
    request: urllib.request.Request = urllib.request.Request(
        url, method=method, data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read() or "null")


def run_graphql(query: str, **variables: object) -> JsonObject:
    response: JsonObject = github_request("POST", "https://api.github.com/graphql",
                                          {"query": query, "variables": variables})
    if response.get("errors"):
        sys.exit(f"GraphQL error: {response['errors']}")
    data: JsonObject = response["data"]
    return data


def parse_sprint_week(node: JsonObject) -> SprintWeek:
    return SprintWeek(id=node["id"], title=node["title"],
                      start_date=date.fromisoformat(node["startDate"]), duration_days=node["duration"])


def load_project() -> tuple[str, str, WeekField]:
    data: JsonObject = run_graphql("""query($owner:String!,$number:Int!){repositoryOwner(login:$owner){
      ... on ProjectV2Owner{projectV2(number:$number){
        id title
        field(name:"Week"){... on ProjectV2IterationField{id configuration{
          iterations{id title startDate duration} completedIterations{id title startDate duration}}}}}}}}""",
                                   owner=PROJECT_OWNER, number=PROJECT_NUMBER)
    project: JsonObject = data["repositoryOwner"]["projectV2"]
    configuration: JsonObject = project["field"]["configuration"]
    weeks: list[SprintWeek] = [parse_sprint_week(node) for node in
                               configuration["iterations"] + configuration["completedIterations"]]
    return project["id"], project["title"], WeekField(id=project["field"]["id"], weeks=weeks)


def parse_project_item(node: JsonObject) -> ProjectItem:
    content: JsonObject = node["content"] or {}
    week: JsonObject = node["week"] or {}
    return ProjectItem(
        id=node["id"],
        title=content.get("title", "?"),
        status=(node["status"] or {}).get("name"),
        week_id=week.get("iterationId"),
        week_title=week.get("title"),
        week_start_date=date.fromisoformat(week["startDate"]) if week.get("startDate") else None,
        issue_number=content.get("number"),
        issue_url=content.get("url"),
        issue_state=content.get("state"),
        assignee_logins=[assignee["login"] for assignee in content.get("assignees", {}).get("nodes", [])],
    )


def load_project_items(project_id: str) -> list[ProjectItem]:
    project_items: list[ProjectItem] = []
    page_cursor: str | None = None
    while True:
        page: JsonObject = run_graphql("""query($projectId:ID!,$after:String){node(id:$projectId){
          ... on ProjectV2{items(first:100,after:$after){
            pageInfo{hasNextPage endCursor}
            nodes{id isArchived
              status: fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}
              week: fieldValueByName(name:"Week"){... on ProjectV2ItemFieldIterationValue{iterationId title startDate}}
              content{
                ... on Issue{title number url state assignees(first:10){nodes{login}}}
                ... on PullRequest{title number url state assignees(first:10){nodes{login}}}
                ... on DraftIssue{title assignees(first:10){nodes{login}}}}}}}}}""",
                                       projectId=project_id, after=page_cursor)["node"]["items"]
        project_items += [parse_project_item(node) for node in page["nodes"] if not node["isArchived"]]
        if not page["pageInfo"]["hasNextPage"]:
            return project_items
        page_cursor = page["pageInfo"]["endCursor"]


def current_or_next_week(weeks: list[SprintWeek]) -> SprintWeek:
    weeks_containing_today: list[SprintWeek] = [week for week in weeks if week.contains(TODAY)]
    upcoming_weeks: list[SprintWeek] = sorted((week for week in weeks if week.start_date > TODAY),
                                              key=lambda week: week.start_date)
    candidate_weeks: list[SprintWeek] = weeks_containing_today or upcoming_weeks
    if not candidate_weeks:
        sys.exit("No current or future week exists; add weeks to the Week field.")
    return candidate_weeks[0]


def move_item_to_week(project_id: str, week_field_id: str, item: ProjectItem, target_week: SprintWeek) -> None:
    run_graphql("""mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!,$weekId:String!){
      updateProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId,
        value:{iterationId:$weekId}}){projectV2Item{id}}}""",
                projectId=project_id, itemId=item.id, fieldId=week_field_id, weekId=target_week.id)


def add_weeks_if_running_low(week_field: WeekField) -> list[str]:
    future_week_count: int = sum(1 for week in week_field.weeks if week.start_date > TODAY)
    if future_week_count >= MINIMUM_FUTURE_WEEKS:
        return []
    weeks_by_start: list[SprintWeek] = sorted(week_field.weeks, key=lambda week: week.start_date)
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
                    fieldId=week_field.id,
                    configuration={"startDate": existing_weeks[0]["startDate"], "duration": WEEK_LENGTH_DAYS,
                                   "iterations": existing_weeks + new_weeks})
    return [new_week["title"] for new_week in new_weeks]


def repository_collaborator_logins() -> set[str]:
    collaborators: list[JsonObject] = github_request(
        "GET", f"https://api.github.com/repos/{SPRINT_LOG_REPOSITORY}/collaborators?per_page=100")
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
        searchQuery=f'repo:{SPRINT_LOG_REPOSITORY} is:issue in:title "{SPRINT_LOG_ISSUE_TITLE}"')["search"]["nodes"]
    for issue in search_results:
        if issue.get("title") == SPRINT_LOG_ISSUE_TITLE:
            existing_issue_number: int = issue["number"]
            return existing_issue_number
    created_issue: JsonObject = github_request("POST", f"https://api.github.com/repos/{SPRINT_LOG_REPOSITORY}/issues", {
        "title": SPRINT_LOG_ISSUE_TITLE,
        "body": "Weekly sprint summaries, posted every Monday by `.github/workflows/sprint-rollover.yml`."})
    created_issue_number: int = created_issue["number"]
    return created_issue_number


def post_sprint_summary(summary: str) -> None:
    if IS_DRY_RUN:
        print("\n--- summary (not posted, dry run) ---\n" + summary)
        return
    sprint_log_issue_number: int = find_or_create_sprint_log_issue_number()
    github_request("POST", f"https://api.github.com/repos/{SPRINT_LOG_REPOSITORY}/issues/{sprint_log_issue_number}/comments",
                   {"body": summary})
    print(f"Posted summary on {SPRINT_LOG_REPOSITORY}#{sprint_log_issue_number}")


def main() -> None:
    project_id: str
    project_title: str
    week_field: WeekField
    project_id, project_title, week_field = load_project()
    print(f"{project_title}: today is {TODAY}{' (dry run)' if IS_DRY_RUN else ''}")

    target_week: SprintWeek = current_or_next_week(week_field.weeks)
    earlier_weeks: list[SprintWeek] = sorted((week for week in week_field.weeks if week.start_date < target_week.start_date),
                                             key=lambda week: week.start_date)
    previous_week: SprintWeek | None = earlier_weeks[-1] if earlier_weeks else None
    print(f"Target week: {target_week.title}")

    project_items: list[ProjectItem] = load_project_items(project_id)
    carried_over_items: list[ProjectItem] = [
        item for item in project_items
        if item.week_start_date and item.week_start_date < target_week.start_date and not item.is_finished]
    for item in carried_over_items:
        print(f"Move {item.summary_line()[2:]}: {item.week_title} -> {target_week.title}")
        if not IS_DRY_RUN:
            move_item_to_week(project_id, week_field.id, item, target_week)
    print(f"Carried over {len(carried_over_items)} card(s)")

    for added_week_title in add_weeks_if_running_low(week_field):
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
