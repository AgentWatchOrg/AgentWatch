from datetime import date, datetime
from zoneinfo import ZoneInfo

PROJECT_TIME_ZONE: ZoneInfo = ZoneInfo("America/Edmonton")


def today_in_project_time_zone() -> date:
    return datetime.now(PROJECT_TIME_ZONE).date()
