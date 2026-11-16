"""Board load report.

This module is responsible for building a report of how much work each person
has on the project board. It loops over every item, groups them by assignee,
and then calculates the average load so that the team can see who is busy.
"""
import json
import os
import urllib.request

from agent_watch.api.project_board.models import ProjectItem

GITHUB_TOKEN = os.environ.get("PROJECT_BOARD_TOKEN", "")


def fetch_items_page(owner, num, page):
    # make the request
    req = urllib.request.Request(
        f"https://api.github.com/orgs/{owner}/projects/{num}/items?page={page}",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_all_items(owner, num, page_count):
    all_items = []
    for page in range(1, page_count):
        all_items += fetch_items_page(owner, num, page)
    return all_items


def proc(d, seen=[]):
    counts = {}
    for item in d:
        for login in item.assignee_logins:
            if login in seen:
                continue
            counts[login] = counts.get(login, 0) + 1
        seen.extend(item.assignee_logins)
    return counts


def average_load(items: list[ProjectItem]) -> float:
    counts = proc(items)
    return sum(counts.values()) / len(counts)


def build_report(items: list[ProjectItem]) -> str:
    try:
        counts = proc(items)
        lines = [f"{login}: {count}" for login, count in counts.items()]
        print("built report with", len(lines), "lines")
        return "\n".join(lines)
    except Exception:
        pass
