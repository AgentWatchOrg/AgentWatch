import logging
from typing import Protocol

from agent_watch.api.forwarder.assign_event_identities import EventIdentityAssigner
from agent_watch.api.forwarder.event_buffer import EventBuffer
from agent_watch.api.forwarder.models import ForwardingResult, MalformedSensorRecordError, PlannedForwarding
from agent_watch.api.forwarder.normalize_tetragon_events import normalize_tetragon_record
from agent_watch.api.forwarder.redact_event_values import redact_event
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.models import IngestionBatchResult, RejectedEvent

MAXIMUM_EVENTS_PER_BATCH: int = 1000

logger: logging.Logger = logging.getLogger(__name__)


class EventBatchSender(Protocol):
    def send_event_batch(self, events: list[JsonObject]) -> IngestionBatchResult: ...


def plan_event_forwarding(
        tetragon_records: list[JsonObject], identity_assigner: EventIdentityAssigner) -> PlannedForwarding:
    events: list[JsonObject] = []
    skipped_record_count: int = 0
    for tetragon_record in tetragon_records:
        try:
            normalized_event: JsonObject | None = normalize_tetragon_record(tetragon_record)
        except MalformedSensorRecordError as malformed_record_error:
            logger.warning("Skipping Tetragon record: %s", malformed_record_error)
            normalized_event = None
        if normalized_event is None:
            skipped_record_count += 1
            continue
        events.append(identity_assigner.assign_identity(redact_event(normalized_event)))
    return PlannedForwarding(events=events, skipped_record_count=skipped_record_count)


def send_buffered_events(event_buffer: EventBuffer, event_batch_sender: EventBatchSender) -> IngestionBatchResult:
    accepted_count: int = 0
    rejected_events: list[RejectedEvent] = []
    duplicate_events: list[RejectedEvent] = []
    while event_buffer.unsent_event_count():
        event_batch: list[JsonObject] = event_buffer.unsent_events(MAXIMUM_EVENTS_PER_BATCH)
        batch_result: IngestionBatchResult = event_batch_sender.send_event_batch(event_batch)
        event_buffer.remove_events({event["event_id"] for event in event_batch})
        for rejected_event in batch_result.rejected_events:
            logger.warning("Ingestion rejected event %s: %s", rejected_event.event_id, rejected_event.reason)
        accepted_count += batch_result.accepted_count
        rejected_events += batch_result.rejected_events
        duplicate_events += batch_result.duplicate_events
    return IngestionBatchResult(
        accepted_count=accepted_count, rejected_events=rejected_events, duplicate_events=duplicate_events)


def apply_event_forwarding(planned_forwarding: PlannedForwarding, event_buffer: EventBuffer,
                           event_batch_sender: EventBatchSender) -> IngestionBatchResult:
    event_buffer.add_events(planned_forwarding.events)
    return send_buffered_events(event_buffer, event_batch_sender)


def forward_tetragon_records(
        tetragon_records: list[JsonObject], identity_assigner: EventIdentityAssigner, event_buffer: EventBuffer,
        event_batch_sender: EventBatchSender, is_dry_run: bool) -> ForwardingResult:
    planned_forwarding: PlannedForwarding = plan_event_forwarding(tetragon_records, identity_assigner)
    delivery_result: IngestionBatchResult = (
        IngestionBatchResult(accepted_count=0, rejected_events=[], duplicate_events=[]) if is_dry_run
        else apply_event_forwarding(planned_forwarding, event_buffer, event_batch_sender))
    return ForwardingResult(
        planned_event_count=len(planned_forwarding.events),
        skipped_record_count=planned_forwarding.skipped_record_count,
        accepted_count=delivery_result.accepted_count, rejected_events=delivery_result.rejected_events,
        duplicate_events=delivery_result.duplicate_events, unsent_event_count=event_buffer.unsent_event_count())
