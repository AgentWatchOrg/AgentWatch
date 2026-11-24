from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import EventStore
from agent_watch.api.ingestion.models import EventValidator, IngestionBatchResult, PlannedIngestion, RejectedEvent


def extract_event_id(raw_event: object) -> str | None:
    if not isinstance(raw_event, dict):
        return None
    event_id: object = raw_event.get("event_id")
    return event_id if isinstance(event_id, str) else None


def plan_event_batch_ingestion(
        raw_events: list[JsonObject], schema_validator: EventValidator, event_store: EventStore) -> PlannedIngestion:
    accepted_events: list[tuple[str, JsonObject]] = []
    rejected_events: list[RejectedEvent] = []
    duplicate_events: list[RejectedEvent] = []
    accepted_event_ids_in_batch: set[str] = set()

    for index, raw_event in enumerate(raw_events):
        validation_errors: list[str] = schema_validator.validation_errors(raw_event)
        if validation_errors:
            rejected_events.append(
                RejectedEvent(index=index, event_id=extract_event_id(raw_event), reason="; ".join(validation_errors)))
            continue

        validated_event_id: str = raw_event["event_id"]
        if event_store.contains(validated_event_id) or validated_event_id in accepted_event_ids_in_batch:
            duplicate_events.append(
                RejectedEvent(index=index, event_id=validated_event_id, reason="duplicate event_id"))
            continue

        accepted_events.append((validated_event_id, raw_event))
        accepted_event_ids_in_batch.add(validated_event_id)

    return PlannedIngestion(
        accepted_events=accepted_events, rejected_events=rejected_events, duplicate_events=duplicate_events)


def apply_event_batch_ingestion(planned_ingestion: PlannedIngestion, event_store: EventStore) -> None:
    for event_id, event in planned_ingestion.accepted_events:
        event_store.add(event_id, event)


def ingest_event_batch(
        raw_events: list[JsonObject], schema_validator: EventValidator,
        event_store: EventStore) -> IngestionBatchResult:
    with event_store.lock:
        planned_ingestion: PlannedIngestion = plan_event_batch_ingestion(raw_events, schema_validator, event_store)
        apply_event_batch_ingestion(planned_ingestion, event_store)
    return IngestionBatchResult(
        accepted_count=len(planned_ingestion.accepted_events),
        rejected_events=planned_ingestion.rejected_events,
        duplicate_events=planned_ingestion.duplicate_events)
