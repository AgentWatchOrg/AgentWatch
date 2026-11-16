from project_board_graphql_client import (
    BACKLOG_STATUS, DONE_STATUS, IS_DRY_RUN, PROJECT_REPOSITORY, SPRINT_LOG_ISSUE_TITLE, TODAY, JsonObject,
    ProjectBoard, ProjectItem, SprintWeek, add_issue_to_project, clear_item_week, current_or_next_week,
    load_project_board, load_project_items, run_graphql, set_item_status, set_item_week)


def load_open_issues() -> list[JsonObject]:
    repository_owner: str
    repository_name: str
    repository_owner, repository_name = PROJECT_REPOSITORY.split("/")
    open_issues: list[JsonObject] = []
    page_cursor: str | None = None
    while True:
        page: JsonObject = run_graphql("""query($owner:String!,$name:String!,$after:String){
          repository(owner:$owner,name:$name){issues(states:OPEN,first:100,after:$after){
            pageInfo{hasNextPage endCursor} nodes{id number title}}}}""",
                                       owner=repository_owner, name=repository_name, after=page_cursor)["repository"]["issues"]
        open_issues += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return open_issues
        page_cursor = page["pageInfo"]["endCursor"]


def add_missing_open_issues_to_backlog(board: ProjectBoard, project_items: list[ProjectItem]) -> None:
    issue_numbers_on_board: set[int] = {item.issue_number for item in project_items if item.issue_number}
    for issue in load_open_issues():
        if issue["number"] in issue_numbers_on_board or issue["title"] == SPRINT_LOG_ISSUE_TITLE:
            continue
        print(f"Add #{issue['number']} {issue['title']} to {BACKLOG_STATUS}")
        if not IS_DRY_RUN:
            added_item_id: str = add_issue_to_project(board, issue["id"])
            set_item_status(board, added_item_id, BACKLOG_STATUS)


def synchronize_item(board: ProjectBoard, item: ProjectItem, current_week: SprintWeek) -> None:
    item_label: str = item.summary_line()[2:]
    if item.is_closed and item.status != DONE_STATUS:
        print(f"Mark {item_label} {DONE_STATUS} (issue closed)")
        if not IS_DRY_RUN:
            set_item_status(board, item.id, DONE_STATUS)
        if item.week_id is None:
            print(f"Put {item_label} in {current_week.title}")
            if not IS_DRY_RUN:
                set_item_week(board, item.id, current_week)
    elif item.status is None:
        print(f"Put {item_label} in {BACKLOG_STATUS}")
        if not IS_DRY_RUN:
            set_item_status(board, item.id, BACKLOG_STATUS)
            if item.week_id:
                clear_item_week(board, item.id)
    elif item.status == BACKLOG_STATUS and item.week_id:
        print(f"Remove {item_label} from {item.week_title} (back in {BACKLOG_STATUS})")
        if not IS_DRY_RUN:
            clear_item_week(board, item.id)
    elif item.status != BACKLOG_STATUS and item.week_id is None:
        print(f"Put {item_label} in {current_week.title} (status {item.status})")
        if not IS_DRY_RUN:
            set_item_week(board, item.id, current_week)


def main() -> None:
    board: ProjectBoard = load_project_board()
    current_week: SprintWeek = current_or_next_week(board.weeks)
    print(f"{board.title}: today is {TODAY}, sprint {current_week.title}{' (dry run)' if IS_DRY_RUN else ''}")
    project_items: list[ProjectItem] = load_project_items(board.id)
    add_missing_open_issues_to_backlog(board, project_items)
    for item in project_items:
        synchronize_item(board, item, current_week)


if __name__ == "__main__":
    main()
