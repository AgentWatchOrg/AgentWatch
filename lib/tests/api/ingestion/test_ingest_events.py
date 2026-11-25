from dataclasses import dataclass, field
from threading import Barrier, BrokenBarrierError, Lock, Thread

import pytest

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.api.ingestion.ingest_events import (
    apply_event_batch_ingestion, extract_event_id, ingest_event_batch, plan_event_batch_ingestion)
from agent_watch.api.ingestion.models import IngestionBatchResult, PlannedIngestion
from agent_watch.api.ingestion.schema_validator import SchemaValidator

RENDEZVOUS_TIMEOUT_SECONDS: float = 0.2


def wait_for_a_second_concurrent_caller(rendezvous: Barrier) -> None:
    try:
        rendezvous.wait(timeout=RENDEZVOUS_TIMEOUT_SECONDS)
    except BrokenBarrierError:
        pass


# Makes contains() and add() each block until a second concurrent caller also reaches them, so
# a missing lock around plan/apply reliably makes both callers see the event as new and both add
# it, instead of leaving that outcome to how CPython happens to schedule two fast threads.
@dataclass
class RendezvousingEventStore:
    inner_event_store: InMemoryEventStore
    contains_rendezvous: Barrier
    add_rendezvous: Barrier
    lock: Lock = field(init=False)

    def __post_init__(self) -> None:
        self.lock = self.inner_event_store.lock

    def contains(self, event_id: str) -> bool:
        wait_for_a_second_concurrent_caller(self.contains_rendezvous)
        return self.inner_event_store.contains(event_id)

    def add(self, event_id: str, event: JsonObject) -> None:
        wait_for_a_second_concurrent_caller(self.add_rendezvous)
        self.inner_event_store.add(event_id, event)

    def pop_unexported_events(self) -> list[JsonObject]:
        return self.inner_event_store.pop_unexported_events()


def test_extract_event_id_returns_the_event_id_of_a_well_formed_event(valid_process_exec_event: JsonObject) -> None:
    assert extract_event_id(valid_process_exec_event) == valid_process_exec_event["event_id"]


def test_extract_event_id_returns_none_when_the_event_id_field_is_missing(
        invalid_missing_event_id_event: JsonObject) -> None:
    assert extract_event_id(invalid_missing_event_id_event) is None


@pytest.mark.parametrize(
    "raw_event", ["not-an-object", {"event_id": 1}], ids=["non_object_event", "non_string_event_id"])
def test_extract_event_id_returns_none_for_an_unextractable_event(raw_event: object) -> None:
    assert extract_event_id(raw_event) is None


def test_plan_event_batch_ingestion_accepts_valid_events(
        telemetry_schema_validator: SchemaValidator, event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject, valid_file_access_event: JsonObject) -> None:
    planned_ingestion: PlannedIngestion = plan_event_batch_ingestion(
        [valid_process_exec_event, valid_file_access_event], telemetry_schema_validator, event_store)

    assert [event_id for event_id, _ in planned_ingestion.accepted_events] == [
        valid_process_exec_event["event_id"], valid_file_access_event["event_id"]]
    assert planned_ingestion.rejected_events == []
    assert planned_ingestion.duplicate_events == []


def test_plan_event_batch_ingestion_rejects_a_malformed_event_with_a_reason(
        telemetry_schema_validator: SchemaValidator, event_store: InMemoryEventStore,
        invalid_missing_event_id_event: JsonObject) -> None:
    planned_ingestion: PlannedIngestion = plan_event_batch_ingestion(
        [invalid_missing_event_id_event], telemetry_schema_validator, event_store)

    assert planned_ingestion.accepted_events == []
    assert len(planned_ingestion.rejected_events) == 1
    assert "event_id" in planned_ingestion.rejected_events[0].reason


def test_plan_event_batch_ingestion_rejects_one_event_without_affecting_the_others(
        telemetry_schema_validator: SchemaValidator, event_store: InMemoryEventStore,
        invalid_missing_event_id_event: JsonObject, valid_process_exec_event: JsonObject) -> None:
    planned_ingestion: PlannedIngestion = plan_event_batch_ingestion(
        [invalid_missing_event_id_event, valid_process_exec_event], telemetry_schema_validator, event_store)

    assert len(planned_ingestion.rejected_events) == 1
    assert [event_id for event_id, _ in planned_ingestion.accepted_events] == [valid_process_exec_event["event_id"]]


def test_plan_event_batch_ingestion_reports_an_event_already_in_the_store_as_duplicate(
        telemetry_schema_validator: SchemaValidator, event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject) -> None:
    event_store.add(valid_process_exec_event["event_id"], valid_process_exec_event)

    planned_ingestion: PlannedIngestion = plan_event_batch_ingestion(
        [valid_process_exec_event], telemetry_schema_validator, event_store)

    assert planned_ingestion.accepted_events == []
    assert [duplicate.event_id for duplicate in planned_ingestion.duplicate_events] == [
        valid_process_exec_event["event_id"]]


def test_plan_event_batch_ingestion_reports_a_repeated_event_in_the_same_batch_as_duplicate(
        telemetry_schema_validator: SchemaValidator, event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject) -> None:
    planned_ingestion: PlannedIngestion = plan_event_batch_ingestion(
        [valid_process_exec_event, valid_process_exec_event], telemetry_schema_validator, event_store)

    assert len(planned_ingestion.accepted_events) == 1
    assert len(planned_ingestion.duplicate_events) == 1


def test_apply_event_batch_ingestion_adds_only_the_accepted_events_to_the_store(
        telemetry_schema_validator: SchemaValidator, event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject, invalid_missing_event_id_event: JsonObject) -> None:
    planned_ingestion: PlannedIngestion = plan_event_batch_ingestion(
        [valid_process_exec_event, invalid_missing_event_id_event], telemetry_schema_validator, event_store)

    apply_event_batch_ingestion(planned_ingestion, event_store)

    assert event_store.pop_unexported_events() == [valid_process_exec_event]


def test_ingest_event_batch_returns_counts_for_each_outcome(
        telemetry_schema_validator: SchemaValidator, event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject, invalid_missing_event_id_event: JsonObject) -> None:
    event_store.add(valid_process_exec_event["event_id"], valid_process_exec_event)

    ingestion_result: IngestionBatchResult = ingest_event_batch(
        [valid_process_exec_event, invalid_missing_event_id_event], telemetry_schema_validator, event_store)

    assert ingestion_result.accepted_count == 0
    assert len(ingestion_result.rejected_events) == 1
    assert len(ingestion_result.duplicate_events) == 1


def test_ingest_event_batch_makes_newly_accepted_events_available_for_export(
        telemetry_schema_validator: SchemaValidator, event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject) -> None:
    ingest_event_batch([valid_process_exec_event], telemetry_schema_validator, event_store)

    assert event_store.pop_unexported_events() == [valid_process_exec_event]


def test_ingest_event_batch_exports_a_concurrently_replayed_event_exactly_once(
        telemetry_schema_validator: SchemaValidator, event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject) -> None:
    rendezvousing_event_store: RendezvousingEventStore = RendezvousingEventStore(event_store, Barrier(2), Barrier(2))
    results: list[IngestionBatchResult] = []

    def ingest_once() -> None:
        results.append(
            ingest_event_batch([valid_process_exec_event], telemetry_schema_validator, rendezvousing_event_store))

    first_thread: Thread = Thread(target=ingest_once)
    second_thread: Thread = Thread(target=ingest_once)
    first_thread.start()
    second_thread.start()
    first_thread.join()
    second_thread.join()

    assert sum(result.accepted_count for result in results) == 1
    assert event_store.pop_unexported_events() == [valid_process_exec_event]
