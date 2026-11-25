import json
import logging
from datetime import datetime
from typing import Protocol

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import EventStore
from agent_watch.api.splunk_export.models import (
    TELEMETRY_SOURCE, TELEMETRY_SOURCETYPE, ExportResult, HecExportProgress, SplunkExportError)

MAXIMUM_EVENTS_PER_HEC_REQUEST: int = 100
MAXIMUM_BYTES_PER_HEC_REQUEST: int = 512_000

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
    hec_event_batches: list[list[JsonObject]] = [[]]
    batch_byte_count: int = 0
    for event in events:
        hec_event: JsonObject = build_hec_event(event, index)
        hec_event_byte_count: int = len(json.dumps(hec_event).encode("utf-8"))
        is_batch_full: bool = (len(hec_event_batches[-1]) >= MAXIMUM_EVENTS_PER_HEC_REQUEST
                               or batch_byte_count + hec_event_byte_count > MAXIMUM_BYTES_PER_HEC_REQUEST)
        if hec_event_batches[-1] and is_batch_full:
            hec_event_batches.append([])
            batch_byte_count = 0
        hec_event_batches[-1].append(hec_event)
        batch_byte_count += hec_event_byte_count
    return [hec_event_batch for hec_event_batch in hec_event_batches if hec_event_batch]


def apply_hec_event_batches(hec_event_batches: list[list[JsonObject]], hec_event_sender: HecEventSender,
                            export_progress: HecExportProgress) -> None:
    for hec_event_batch in hec_event_batches:
        try:
            hec_event_sender.send_hec_events(hec_event_batch)
        except SplunkExportError as export_error:
            if export_error.is_retryable:
                logger.error("Splunk export failed: %s", export_error)
                return
            rejected_event_ids: list[str] = [str(hec_event["event"].get("event_id")) for hec_event in hec_event_batch]
            logger.error("Splunk permanently rejected %d event(s), dropping %s: %s", len(hec_event_batch),
                         ", ".join(rejected_event_ids), export_error)
            export_progress.dropped_event_count += len(hec_event_batch)
            continue
        export_progress.sent_event_count += len(hec_event_batch)


def requeue_unsent_events(event_store: EventStore, unexported_events: list[JsonObject],
                          handled_event_count: int) -> int:
    unsent_events: list[JsonObject] = unexported_events[handled_event_count:]
    if unsent_events:
        event_store.requeue_unexported_events(unsent_events)
        logger.error("%d event(s) were not exported to Splunk and are kept for the next export", len(unsent_events))
    return len(unsent_events)


def export_unexported_events(
        event_store: EventStore, hec_event_sender: HecEventSender, index: str | None) -> ExportResult:
    unexported_events: list[JsonObject] = event_store.pop_unexported_events()
    export_progress: HecExportProgress = HecExportProgress()
    try:
        apply_hec_event_batches(plan_hec_event_batches(unexported_events, index), hec_event_sender, export_progress)
    finally:
        unsent_event_count: int = requeue_unsent_events(
            event_store, unexported_events, export_progress.sent_event_count + export_progress.dropped_event_count)
    if export_progress.sent_event_count and not unsent_event_count:
        logger.info("Exported %d event(s) to Splunk", export_progress.sent_event_count)
    return ExportResult(exported_event_count=export_progress.sent_event_count,
                        dropped_event_count=export_progress.dropped_event_count,
                        failed_event_count=unsent_event_count)
