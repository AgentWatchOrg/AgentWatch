from dataclasses import dataclass
from datetime import date, timedelta

BACKLOG_STATUS: str = "Backlog"
DONE_STATUS: str = "Done"
SPRINT_LOG_ISSUE_TITLE: str = "Sprint Log"
CLOSED_ISSUE_STATES: frozenset[str] = frozenset({"CLOSED", "MERGED"})


class NoSprintWeekError(Exception):
    pass


class WebhookSignatureError(Exception):
    pass


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
class NewSprintWeek:
    title: str
    start_date: date
    duration_days: int


@dataclass(frozen=True)
class ProjectBoard:
    id: str
    title: str
    week_field_id: str
    weeks: list[SprintWeek]
    status_field_id: str
    status_option_ids_by_name: dict[str, str]

    def current_or_next_week(self, today: date) -> SprintWeek:
        weeks_containing_today: list[SprintWeek] = [week for week in self.weeks if week.contains(today)]
        upcoming_weeks: list[SprintWeek] = sorted((week for week in self.weeks if week.start_date > today),
                                                  key=lambda week: week.start_date)
        candidate_weeks: list[SprintWeek] = weeks_containing_today or upcoming_weeks
        if not candidate_weeks:
            raise NoSprintWeekError("No current or future week exists; add weeks to the Week field.")
        return candidate_weeks[0]


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
    def is_closed(self) -> bool:
        return self.issue_state in CLOSED_ISSUE_STATES

    @property
    def is_finished(self) -> bool:
        return self.status == DONE_STATUS or self.is_closed


@dataclass(frozen=True)
class OpenIssue:
    id: str
    number: int
    title: str
