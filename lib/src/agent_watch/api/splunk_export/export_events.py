import logging
from datetime import datetime
from typing import Protocol

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import EventStore
from agent_watch.api.splunk_export.models import (
    TELEMETRY_SOURCE, TELEMETRY_SOURCETYPE, ExportResult, SplunkExportError)

MAXIMUM_EVENTS_PER_HEC_REQUEST: int = 100

logger: logging.Logger = logging.getLogger(__name__)


class HecEventSender(Protocol):
    def send_hec_events(self, hec_events: list[JsonObject]) -> None: ...


def epoch_seconds_from_timestamp(timestamp: str) -> float | None:
    try:
        return datetime.fromisoformat(timestamp.upper()).timestamp()
    except ValueError:
        return None


def build_hec_event(event: JsonObject, index: str | None) -> JsonObject:
    hec_event: JsonObject = {"host": event["host"], "source": TELEMETRY_SOURCE, "sourcetype": TELEMETRY_SOURCETYPE,
                             "event": event}
    event_time: float | None = epoch_seconds_from_timestamp(event["timestamp"])
    if event_time is not None:
        hec_event["time"] = event_time
    if index:
        hec_event["index"] = index
    return hec_event


def plan_hec_event_batches(events: list[JsonObject], index: str | None) -> list[list[JsonObject]]:
    hec_events: list[JsonObject] = [build_hec_event(event, index) for event in events]
    return [hec_events[start:start + MAXIMUM_EVENTS_PER_HEC_REQUEST]
            for start in range(0, len(hec_events), MAXIMUM_EVENTS_PER_HEC_REQUEST)]


def apply_hec_event_batches(hec_event_batches: list[list[JsonObject]], hec_event_sender: HecEventSender) -> int:
    sent_event_count: int = 0
    for hec_event_batch in hec_event_batches:
        try:
            hec_event_sender.send_hec_events(hec_event_batch)
        except SplunkExportError as export_error:
            logger.error("Splunk export failed: %s", export_error)
            return sent_event_count
        sent_event_count += len(hec_event_batch)
    return sent_event_count


def export_unexported_events(
        event_store: EventStore, hec_event_sender: HecEventSender, index: str | None) -> ExportResult:
    unexported_events: list[JsonObject] = event_store.pop_unexported_events()
    if not unexported_events:
        return ExportResult(exported_event_count=0, failed_event_count=0)
    sent_event_count: int = apply_hec_event_batches(plan_hec_event_batches(unexported_events, index), hec_event_sender)
    unsent_events: list[JsonObject] = unexported_events[sent_event_count:]
    if unsent_events:
        event_store.requeue_unexported_events(unsent_events)
        logger.error("%d event(s) were not exported to Splunk and are kept for the next export", len(unsent_events))
    else:
        logger.info("Exported %d event(s) to Splunk", sent_event_count)
    return ExportResult(exported_event_count=sent_event_count, failed_event_count=len(unsent_events))
