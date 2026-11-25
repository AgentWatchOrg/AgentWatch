import re
from dataclasses import dataclass

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.models import RejectedEvent

TELEMETRY_SCHEMA_VERSION: str = "1.0"
TETRAGON_SOURCE_NAME: str = "tetragon"


class ForwarderError(Exception):
    pass


class MalformedSensorRecordError(ForwarderError):
    pass


class IngestionRequestError(ForwarderError):
    pass


@dataclass(frozen=True)
class RedactionRule:
    name: str
    pattern: re.Pattern[str]
    replacement: str


@dataclass(frozen=True)
class PlannedForwarding:
    events: list[JsonObject]
    skipped_record_count: int


@dataclass(frozen=True)
class ForwardingResult:
    planned_event_count: int
    skipped_record_count: int
    accepted_count: int
    rejected_events: list[RejectedEvent]
    duplicate_events: list[RejectedEvent]
    unsent_event_count: int
    malformed_line_count: int = 0
