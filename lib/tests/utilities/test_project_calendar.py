from datetime import date, datetime, timezone, tzinfo
from typing import Self

import pytest

from agent_watch.utilities import project_calendar

SUNDAY_EVENING_IN_CALGARY_AS_UTC: datetime = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls.fromtimestamp(SUNDAY_EVENING_IN_CALGARY_AS_UTC.timestamp(), tz)


def test_today_is_the_calgary_date_not_the_utc_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(project_calendar, "datetime", FrozenDatetime)

    assert project_calendar.today_in_project_time_zone() == date(2026, 11, 15)
