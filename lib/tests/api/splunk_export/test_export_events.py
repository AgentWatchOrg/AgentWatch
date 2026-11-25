import http.client
import logging
from typing import Iterator

import pytest
from doubles.splunk_export_test_doubles import (
    EventRejectingHecEventSender, HecEventBatchFactory, RecordingHecEventSender, RecordingHecEventSenderFactory)

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.api.splunk_export import export_events
from agent_watch.api.splunk_export.export_events import (
    apply_hec_event_batches, build_hec_event, epoch_seconds_from_timestamp, export_unexported_events,
    plan_hec_event_batches, requeue_unsent_events, split_in_half)
from agent_watch.api.splunk_export.models import ExportResult, HecExportProgress, SplunkExportError


@pytest.fixture
def accepted_events(valid_process_exec_event: JsonObject, valid_file_access_event: JsonObject) -> list[JsonObject]:
    return [valid_process_exec_event, valid_file_access_event]


@pytest.fixture
def event_store_with_accepted_events(
        event_store: InMemoryEventStore, accepted_events: list[JsonObject]) -> InMemoryEventStore:
    for accepted_event in accepted_events:
        event_store.add(accepted_event["event_id"], accepted_event)
    return event_store


@pytest.fixture
def export_progress() -> HecExportProgress:
    return HecExportProgress()


@pytest.fixture
def permanent_rejection() -> SplunkExportError:
    return SplunkExportError("returned HTTP 413: Content too large", is_retryable=False)


@pytest.fixture
def make_hec_event_batch() -> HecEventBatchFactory:
    def build_hec_event_batch(event_ids: str) -> list[JsonObject]:
        return [{"event": {"event_id": event_id}} for event_id in event_ids]
    return build_hec_event_batch


@pytest.fixture
def make_recording_hec_event_sender() -> RecordingHecEventSenderFactory:
    def build_recording_hec_event_sender(failing_request_numbers: frozenset[int],
                                         failure: Exception | None = None) -> RecordingHecEventSender:
        if failure is None:
            return RecordingHecEventSender(failing_request_numbers)
        return RecordingHecEventSender(failing_request_numbers, failure=failure)
    return build_recording_hec_event_sender


@pytest.fixture
def sender_rejecting_event_c() -> EventRejectingHecEventSender:
    return EventRejectingHecEventSender("c")


@pytest.fixture
def one_event_per_hec_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_events, "MAXIMUM_EVENTS_PER_HEC_REQUEST", 1)


@pytest.fixture
def agent_watch_error_logs(
        caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.LogCaptureFixture]:
    monkeypatch.setattr(logging.getLogger("agent_watch"), "propagate", True)
    with caplog.at_level(logging.ERROR, logger="agent_watch"):
        yield caplog


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
    assert (hec_event["source"], hec_event["sourcetype"]) == ("agentwatch:ingestion", "agentwatch:telemetry")
    assert hec_event["time"] == epoch_seconds_from_timestamp(valid_process_exec_event["timestamp"])
    assert "index" not in hec_event


def test_build_hec_event_sets_the_configured_index(valid_process_exec_event: JsonObject) -> None:
    assert build_hec_event(valid_process_exec_event, index="agentwatch")["index"] == "agentwatch"


def test_plan_hec_event_batches_splits_events_into_requests(
        monkeypatch: pytest.MonkeyPatch, valid_process_exec_event: JsonObject) -> None:
    monkeypatch.setattr(export_events, "MAXIMUM_EVENTS_PER_HEC_REQUEST", 2)

    hec_event_batches: list[list[JsonObject]] = plan_hec_event_batches([valid_process_exec_event] * 5, index=None)

    assert [len(hec_event_batch) for hec_event_batch in hec_event_batches] == [2, 2, 1]


def test_plan_hec_event_batches_starts_a_new_request_before_the_byte_limit(
        monkeypatch: pytest.MonkeyPatch, valid_process_exec_event: JsonObject) -> None:
    monkeypatch.setattr(export_events, "MAXIMUM_BYTES_PER_HEC_REQUEST", 1)

    hec_event_batches: list[list[JsonObject]] = plan_hec_event_batches([valid_process_exec_event] * 3, index=None)

    assert [len(hec_event_batch) for hec_event_batch in hec_event_batches] == [1, 1, 1]


def test_apply_hec_event_batches_stops_at_a_retryable_failure(
        make_hec_event_batch: HecEventBatchFactory, make_recording_hec_event_sender: RecordingHecEventSenderFactory,
        export_progress: HecExportProgress) -> None:
    hec_event_batches: list[list[JsonObject]] = [make_hec_event_batch("ab"), make_hec_event_batch("c"),
                                                 make_hec_event_batch("d")]

    apply_hec_event_batches(hec_event_batches, make_recording_hec_event_sender(frozenset({2})), export_progress)

    assert export_progress == HecExportProgress(sent_event_count=2, dropped_event_count=0)


def test_apply_hec_event_batches_drops_a_permanently_rejected_event_and_continues(
        make_hec_event_batch: HecEventBatchFactory, make_recording_hec_event_sender: RecordingHecEventSenderFactory,
        permanent_rejection: SplunkExportError, export_progress: HecExportProgress,
        agent_watch_error_logs: pytest.LogCaptureFixture) -> None:
    sender_rejecting_first_request: RecordingHecEventSender = make_recording_hec_event_sender(
        frozenset({1}), failure=permanent_rejection)

    apply_hec_event_batches([make_hec_event_batch("a"), make_hec_event_batch("b")], sender_rejecting_first_request,
                            export_progress)

    assert export_progress == HecExportProgress(sent_event_count=1, dropped_event_count=1)
    assert "Splunk permanently rejected event a, dropping it" in agent_watch_error_logs.text


def test_apply_hec_event_batches_splits_a_rejected_batch_to_drop_only_the_bad_event(
        make_hec_event_batch: HecEventBatchFactory, sender_rejecting_event_c: EventRejectingHecEventSender,
        export_progress: HecExportProgress) -> None:
    apply_hec_event_batches([make_hec_event_batch("abcd")], sender_rejecting_event_c, export_progress)

    assert sender_rejecting_event_c.accepted_event_ids == ["a", "b", "d"]
    assert sender_rejecting_event_c.sent_batch_sizes == [4, 2, 2, 1, 1]
    assert export_progress == HecExportProgress(sent_event_count=3, dropped_event_count=1)


@pytest.mark.parametrize(("event_ids", "expected_halves"), [("abcd", ["ab", "cd"]), ("abcde", ["ab", "cde"]),
                                                            ("ab", ["a", "b"])], ids=["even", "odd", "pair"])
def test_split_in_half(event_ids: str, expected_halves: list[str],
                       make_hec_event_batch: HecEventBatchFactory) -> None:
    halves: list[list[JsonObject]] = split_in_half(make_hec_event_batch(event_ids))

    assert halves == [make_hec_event_batch(expected_half) for expected_half in expected_halves]


def test_requeue_unsent_events_puts_back_only_the_events_after_the_handled_ones(
        event_store: InMemoryEventStore, accepted_events: list[JsonObject]) -> None:
    unsent_event_count: int = requeue_unsent_events(event_store, accepted_events, handled_event_count=1)

    assert unsent_event_count == 1
    assert event_store.pop_unexported_events() == accepted_events[1:]


@pytest.mark.usefixtures("one_event_per_hec_request")
def test_export_unexported_events_keeps_only_the_events_after_a_failed_request(
        event_store_with_accepted_events: InMemoryEventStore, accepted_events: list[JsonObject],
        make_recording_hec_event_sender: RecordingHecEventSenderFactory) -> None:
    export_result: ExportResult = export_unexported_events(
        event_store_with_accepted_events, make_recording_hec_event_sender(frozenset({2})), index=None)

    assert export_result == ExportResult(exported_event_count=1, dropped_event_count=0, failed_event_count=1)
    assert event_store_with_accepted_events.pop_unexported_events() == accepted_events[1:]


@pytest.mark.usefixtures("one_event_per_hec_request")
def test_export_unexported_events_does_not_let_a_rejected_event_block_the_queue(
        event_store_with_accepted_events: InMemoryEventStore, accepted_events: list[JsonObject],
        make_recording_hec_event_sender: RecordingHecEventSenderFactory,
        permanent_rejection: SplunkExportError) -> None:
    sender_rejecting_first_request: RecordingHecEventSender = make_recording_hec_event_sender(
        frozenset({1}), failure=permanent_rejection)

    export_result: ExportResult = export_unexported_events(
        event_store_with_accepted_events, sender_rejecting_first_request, index=None)

    assert export_result == ExportResult(exported_event_count=1, dropped_event_count=1, failed_event_count=0)
    assert sender_rejecting_first_request.sent_events() == accepted_events[1:]
    assert event_store_with_accepted_events.pop_unexported_events() == []


@pytest.mark.usefixtures("one_event_per_hec_request")
def test_export_unexported_events_keeps_unsent_events_when_an_unexpected_error_escapes(
        event_store_with_accepted_events: InMemoryEventStore, accepted_events: list[JsonObject],
        make_recording_hec_event_sender: RecordingHecEventSenderFactory) -> None:
    sender_dropping_second_request: RecordingHecEventSender = make_recording_hec_event_sender(
        frozenset({2}), failure=http.client.RemoteDisconnected("Remote end closed connection without response"))

    with pytest.raises(http.client.RemoteDisconnected):
        export_unexported_events(event_store_with_accepted_events, sender_dropping_second_request, index=None)

    assert event_store_with_accepted_events.pop_unexported_events() == accepted_events[1:]


def test_export_unexported_events_sends_every_accepted_event_once(
        event_store_with_accepted_events: InMemoryEventStore, accepted_events: list[JsonObject],
        recording_hec_event_sender: RecordingHecEventSender) -> None:
    export_result: ExportResult = export_unexported_events(
        event_store_with_accepted_events, recording_hec_event_sender, index=None)

    assert export_result == ExportResult(exported_event_count=2, dropped_event_count=0, failed_event_count=0)
    assert recording_hec_event_sender.sent_events() == accepted_events
    assert event_store_with_accepted_events.pop_unexported_events() == []


def test_export_unexported_events_keeps_events_and_logs_an_error_when_splunk_fails(
        event_store_with_accepted_events: InMemoryEventStore, accepted_events: list[JsonObject],
        make_recording_hec_event_sender: RecordingHecEventSenderFactory,
        agent_watch_error_logs: pytest.LogCaptureFixture) -> None:
    export_result: ExportResult = export_unexported_events(
        event_store_with_accepted_events, make_recording_hec_event_sender(frozenset({1})), index=None)

    assert export_result == ExportResult(exported_event_count=0, dropped_event_count=0, failed_event_count=2)
    assert "Splunk export failed: Could not reach Splunk HEC" in agent_watch_error_logs.text
    assert event_store_with_accepted_events.pop_unexported_events() == accepted_events


def test_export_unexported_events_sends_nothing_when_no_events_are_waiting(
        event_store: InMemoryEventStore, recording_hec_event_sender: RecordingHecEventSender) -> None:
    export_result: ExportResult = export_unexported_events(event_store, recording_hec_event_sender, index=None)

    assert export_result == ExportResult(exported_event_count=0, dropped_event_count=0, failed_event_count=0)
    assert recording_hec_event_sender.sent_batches == []
