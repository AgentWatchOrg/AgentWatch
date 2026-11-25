import json

import pytest
from doubles.forwarder_test_doubles import (
    FAKE_SECRET_VALUES, LiveIngestionServer, RecordingEventBatchSender, TetragonRecordLoader)
from telemetry_fixture_paths import TETRAGON_EXPECTED_FIXTURE_DIRECTORY, load_json_object

from agent_watch.api.forwarder import forward_events
from agent_watch.api.forwarder.assign_event_identities import EventIdentityAssigner
from agent_watch.api.forwarder.event_buffer import InMemoryEventBuffer
from agent_watch.api.forwarder.forward_events import (
    apply_event_forwarding, forward_tetragon_records, plan_event_forwarding, send_buffered_events)
from agent_watch.api.forwarder.ingestion_client import IngestionClient
from agent_watch.api.forwarder.models import ForwardingResult, IngestionRequestError, PlannedForwarding
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.models import IngestionBatchResult
from agent_watch.api.ingestion.schema_validator import SchemaValidator

@pytest.mark.parametrize("fixture_name", ["process-exec", "file-access", "network-connect"])
def test_plan_event_forwarding_produces_the_expected_schema_valid_event(
        fixture_name: str, load_tetragon_record: TetragonRecordLoader, identity_assigner: EventIdentityAssigner,
        telemetry_schema_validator: SchemaValidator) -> None:
    planned_forwarding: PlannedForwarding = plan_event_forwarding(
        [load_tetragon_record(fixture_name)], identity_assigner)

    expected_event: JsonObject = load_json_object(TETRAGON_EXPECTED_FIXTURE_DIRECTORY / f"{fixture_name}.json")
    assert planned_forwarding.events == [expected_event]
    assert telemetry_schema_validator.validation_errors(expected_event) == []


def test_plan_event_forwarding_counts_unsupported_and_malformed_records(
        load_tetragon_record: TetragonRecordLoader, identity_assigner: EventIdentityAssigner) -> None:
    planned_forwarding: PlannedForwarding = plan_event_forwarding(
        [load_tetragon_record("process-exit"), {"process_exec": {"process": {}}}, load_tetragon_record("process-exec")],
        identity_assigner)

    assert planned_forwarding.skipped_record_count == 2
    assert len(planned_forwarding.events) == 1


def test_fake_credentials_never_reach_the_buffer_or_the_sent_batch(
        load_tetragon_record: TetragonRecordLoader, identity_assigner: EventIdentityAssigner,
        event_buffer: InMemoryEventBuffer) -> None:
    failing_sender: RecordingEventBatchSender = RecordingEventBatchSender(failing_attempt_count=1)
    planned_forwarding: PlannedForwarding = plan_event_forwarding(
        [load_tetragon_record("process-exec-with-fake-credentials")], identity_assigner)

    with pytest.raises(IngestionRequestError):
        apply_event_forwarding(planned_forwarding, event_buffer, failing_sender)

    serialized_buffer: str = json.dumps(event_buffer.unsent_events(10))
    serialized_batch: str = json.dumps({"events": failing_sender.sent_batches[0]})
    for secret_value in FAKE_SECRET_VALUES:
        assert secret_value not in serialized_buffer
        assert secret_value not in serialized_batch


def test_send_buffered_events_keeps_events_after_a_failed_request_and_resends_the_same_ids(
        load_tetragon_record: TetragonRecordLoader, identity_assigner: EventIdentityAssigner,
        event_buffer: InMemoryEventBuffer) -> None:
    sender_failing_once: RecordingEventBatchSender = RecordingEventBatchSender(failing_attempt_count=1)
    event_buffer.add_events(plan_event_forwarding([load_tetragon_record("process-exec")], identity_assigner).events)

    with pytest.raises(IngestionRequestError):
        send_buffered_events(event_buffer, sender_failing_once)
    assert event_buffer.unsent_event_count() == 1
    batch_result: IngestionBatchResult = send_buffered_events(event_buffer, sender_failing_once)

    first_attempt, second_attempt = sender_failing_once.sent_batches
    assert [event["event_id"] for event in first_attempt] == [event["event_id"] for event in second_attempt]
    assert batch_result.accepted_count == 1
    assert event_buffer.unsent_event_count() == 0


def test_send_buffered_events_splits_the_buffer_into_batches(
        monkeypatch: pytest.MonkeyPatch, event_buffer: InMemoryEventBuffer,
        recording_sender: RecordingEventBatchSender) -> None:
    monkeypatch.setattr(forward_events, "MAXIMUM_EVENTS_PER_BATCH", 2)
    event_buffer.add_events([{"event_id": event_id} for event_id in ["a", "b", "c"]])

    batch_result: IngestionBatchResult = send_buffered_events(event_buffer, recording_sender)

    assert [len(sent_batch) for sent_batch in recording_sender.sent_batches] == [2, 1]
    assert batch_result.accepted_count == 3


def test_send_buffered_events_reports_per_event_rejections(event_buffer: InMemoryEventBuffer) -> None:
    rejecting_sender: RecordingEventBatchSender = RecordingEventBatchSender(rejected_event_ids=frozenset({"b"}))
    event_buffer.add_events([{"event_id": "a"}, {"event_id": "b"}])

    batch_result: IngestionBatchResult = send_buffered_events(event_buffer, rejecting_sender)

    assert [rejected_event.event_id for rejected_event in batch_result.rejected_events] == ["b"]
    assert batch_result.accepted_count == 1


def test_forward_tetragon_records_in_a_dry_run_sends_nothing(
        load_tetragon_record: TetragonRecordLoader, identity_assigner: EventIdentityAssigner,
        event_buffer: InMemoryEventBuffer, recording_sender: RecordingEventBatchSender) -> None:
    result: ForwardingResult = forward_tetragon_records(
        [load_tetragon_record("process-exec")], identity_assigner, event_buffer, recording_sender, is_dry_run=True)

    assert result.planned_event_count == 1
    assert recording_sender.sent_batches == []


def test_forward_tetragon_records_delivers_every_event_type_to_ingestion(
        live_ingestion_server: LiveIngestionServer, load_tetragon_record: TetragonRecordLoader,
        identity_assigner: EventIdentityAssigner, event_buffer: InMemoryEventBuffer) -> None:
    ingestion_client: IngestionClient = IngestionClient(live_ingestion_server.url, live_ingestion_server.api_key)
    tetragon_records: list[JsonObject] = [
        load_tetragon_record(fixture_name) for fixture_name in ["process-exec", "file-access", "network-connect"]]

    result: ForwardingResult = forward_tetragon_records(
        tetragon_records, identity_assigner, event_buffer, ingestion_client, is_dry_run=False)

    assert result.accepted_count == 3
    assert result.rejected_events == []
    assert result.unsent_event_count == 0
    assert len(live_ingestion_server.event_store.pop_unexported_events()) == 3


def test_resending_an_accepted_event_to_ingestion_is_reported_as_a_duplicate(
        live_ingestion_server: LiveIngestionServer, load_tetragon_record: TetragonRecordLoader,
        identity_assigner: EventIdentityAssigner, event_buffer: InMemoryEventBuffer) -> None:
    ingestion_client: IngestionClient = IngestionClient(live_ingestion_server.url, live_ingestion_server.api_key)
    planned_forwarding: PlannedForwarding = plan_event_forwarding(
        [load_tetragon_record("process-exec")], identity_assigner)
    apply_event_forwarding(planned_forwarding, event_buffer, ingestion_client)

    resend_result: IngestionBatchResult = apply_event_forwarding(planned_forwarding, event_buffer, ingestion_client)

    assert [duplicate.event_id for duplicate in resend_result.duplicate_events] == [
        planned_forwarding.events[0]["event_id"]]
