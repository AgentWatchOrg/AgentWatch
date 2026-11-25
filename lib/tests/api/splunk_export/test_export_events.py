import http.client
import logging

import pytest
from doubles.splunk_export_test_doubles import RecordingHecEventSender

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.api.splunk_export import export_events
from agent_watch.api.splunk_export.export_events import (
    build_hec_event, epoch_seconds_from_timestamp, export_unexported_events, plan_hec_event_batches,
    requeue_unsent_events)
from agent_watch.api.splunk_export.models import ExportResult


@pytest.fixture
def accepted_events(valid_process_exec_event: JsonObject, valid_file_access_event: JsonObject) -> list[JsonObject]:
    return [valid_process_exec_event, valid_file_access_event]


@pytest.fixture
def event_store_with_accepted_events(
        event_store: InMemoryEventStore, accepted_events: list[JsonObject]) -> InMemoryEventStore:
    for accepted_event in accepted_events:
        event_store.add(accepted_event["event_id"], accepted_event)
    return event_store


@pytest.mark.parametrize(("timestamp", "expected_epoch_seconds"), [
    ("2026-11-18T12:00:00Z", 1795003200.0),
    ("2026-11-18T12:00:00.123456789Z", 1795003200.123456),
    ("2026-11-18T14:00:00+02:00", 1795003200.0),
    ("2026-11-18t12:00:00z", 1795003200.0),
    ("not-a-date", None),
], ids=["utc", "nanoseconds", "offset", "lowercase", "invalid"])
def test_epoch_seconds_from_timestamp(timestamp: str, expected_epoch_seconds: float | None) -> None:
    assert epoch_seconds_from_timestamp(timestamp) == expected_epoch_seconds


def test_build_hec_event_keeps_the_whole_event_and_sets_splunk_metadata(valid_process_exec_event: JsonObject) -> None:
    hec_event: JsonObject = build_hec_event(valid_process_exec_event, index=None)

    assert hec_event["event"] == valid_process_exec_event
    assert hec_event["host"] == valid_process_exec_event["host"]
    assert hec_event["sourcetype"] == "agentwatch:telemetry"
    assert hec_event["time"] == epoch_seconds_from_timestamp(valid_process_exec_event["timestamp"])
    assert "index" not in hec_event


def test_build_hec_event_sets_the_configured_index(valid_process_exec_event: JsonObject) -> None:
    assert build_hec_event(valid_process_exec_event, index="agentwatch")["index"] == "agentwatch"


def test_plan_hec_event_batches_splits_events_into_requests(
        monkeypatch: pytest.MonkeyPatch, valid_process_exec_event: JsonObject) -> None:
    monkeypatch.setattr(export_events, "MAXIMUM_EVENTS_PER_HEC_REQUEST", 2)

    hec_event_batches: list[list[JsonObject]] = plan_hec_event_batches([valid_process_exec_event] * 5, index=None)

    assert [len(hec_event_batch) for hec_event_batch in hec_event_batches] == [2, 2, 1]


def test_requeue_unsent_events_puts_back_only_the_events_after_the_sent_ones(
        event_store: InMemoryEventStore, accepted_events: list[JsonObject]) -> None:
    unsent_event_count: int = requeue_unsent_events(event_store, accepted_events, sent_event_count=1)

    assert unsent_event_count == 1
    assert event_store.pop_unexported_events() == accepted_events[1:]


def test_export_unexported_events_keeps_only_the_events_after_a_failed_request(
        monkeypatch: pytest.MonkeyPatch, event_store_with_accepted_events: InMemoryEventStore,
        accepted_events: list[JsonObject]) -> None:
    monkeypatch.setattr(export_events, "MAXIMUM_EVENTS_PER_HEC_REQUEST", 1)
    sender_failing_second_request: RecordingHecEventSender = RecordingHecEventSender(frozenset({2}))

    export_result: ExportResult = export_unexported_events(
        event_store_with_accepted_events, sender_failing_second_request, index=None)

    assert export_result == ExportResult(exported_event_count=1, failed_event_count=1)
    assert event_store_with_accepted_events.pop_unexported_events() == accepted_events[1:]


def test_export_unexported_events_keeps_unsent_events_when_an_unexpected_error_escapes(
        monkeypatch: pytest.MonkeyPatch, event_store_with_accepted_events: InMemoryEventStore,
        accepted_events: list[JsonObject]) -> None:
    monkeypatch.setattr(export_events, "MAXIMUM_EVENTS_PER_HEC_REQUEST", 1)
    sender_dropping_second_request: RecordingHecEventSender = RecordingHecEventSender(
        frozenset({2}), failure=http.client.RemoteDisconnected("Remote end closed connection without response"))

    with pytest.raises(http.client.RemoteDisconnected):
        export_unexported_events(event_store_with_accepted_events, sender_dropping_second_request, index=None)

    assert event_store_with_accepted_events.pop_unexported_events() == accepted_events[1:]


def test_export_unexported_events_sends_every_accepted_event_once(
        event_store_with_accepted_events: InMemoryEventStore, accepted_events: list[JsonObject],
        recording_hec_event_sender: RecordingHecEventSender) -> None:
    export_result: ExportResult = export_unexported_events(
        event_store_with_accepted_events, recording_hec_event_sender, index=None)

    assert export_result == ExportResult(exported_event_count=2, failed_event_count=0)
    assert recording_hec_event_sender.sent_events() == accepted_events
    assert event_store_with_accepted_events.pop_unexported_events() == []


def test_export_unexported_events_keeps_events_and_logs_an_error_when_splunk_fails(
        event_store_with_accepted_events: InMemoryEventStore, accepted_events: list[JsonObject],
        caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    failing_sender: RecordingHecEventSender = RecordingHecEventSender(frozenset({1}))
    monkeypatch.setattr(logging.getLogger("agent_watch"), "propagate", True)

    with caplog.at_level(logging.ERROR, logger="agent_watch"):
        export_result: ExportResult = export_unexported_events(event_store_with_accepted_events, failing_sender, None)

    assert export_result == ExportResult(exported_event_count=0, failed_event_count=2)
    assert "Splunk export failed: Could not reach Splunk HEC" in caplog.text
    assert event_store_with_accepted_events.pop_unexported_events() == accepted_events


def test_export_unexported_events_sends_nothing_when_no_events_are_waiting(
        event_store: InMemoryEventStore, recording_hec_event_sender: RecordingHecEventSender) -> None:
    export_result: ExportResult = export_unexported_events(event_store, recording_hec_event_sender, index=None)

    assert export_result == ExportResult(exported_event_count=0, failed_event_count=0)
    assert recording_hec_event_sender.sent_batches == []
