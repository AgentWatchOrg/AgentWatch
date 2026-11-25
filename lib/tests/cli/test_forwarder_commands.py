from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from telemetry_fixture_paths import TETRAGON_RAW_FIXTURE_DIRECTORY

from agent_watch.api.forwarder.assign_event_identities import EventIdentityAssigner
from agent_watch.api.forwarder.event_buffer import EventBuffer
from agent_watch.api.forwarder.forward_events import EventBatchSender
from agent_watch.api.forwarder.models import ForwardingResult, IngestionRequestError
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.models import RejectedEvent
from agent_watch.cli import forwarder_commands
from agent_watch.cli.main import agent_watch

FORWARDER_ENVIRONMENT: dict[str, str] = {"INGESTION_URL": "http://127.0.0.1:8000", "INGESTION_API_KEY": "key"}


@pytest.fixture
def tetragon_events_file(tmp_path: Path) -> Path:
    raw_record_lines: list[str] = [
        (TETRAGON_RAW_FIXTURE_DIRECTORY / f"{fixture_name}.json").read_text(encoding="utf-8").replace("\n", "")
        for fixture_name in ["process-exec", "process-exit"]]
    events_file: Path = tmp_path / "tetragon-events.json"
    events_file.write_text("\n".join(raw_record_lines + ["not json"]) + "\n", encoding="utf-8")
    return events_file


def build_forwarding_result(rejected_events: list[RejectedEvent]) -> ForwardingResult:
    return ForwardingResult(planned_event_count=1, skipped_record_count=1, accepted_count=1 - len(rejected_events),
                            rejected_events=rejected_events, duplicate_events=[], unsent_event_count=0)


def test_forward_tetragon_events_reports_the_delivery(
        cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tetragon_events_file: Path) -> None:
    received_record_counts: list[tuple[int, bool]] = []

    def fake_forward_tetragon_records(
            tetragon_records: list[JsonObject], identity_assigner: EventIdentityAssigner, event_buffer: EventBuffer,
            event_batch_sender: EventBatchSender, is_dry_run: bool) -> ForwardingResult:
        received_record_counts.append((len(tetragon_records), is_dry_run))
        return build_forwarding_result([])

    monkeypatch.setattr(forwarder_commands, "forward_tetragon_records", fake_forward_tetragon_records)

    result: Result = cli_runner.invoke(
        agent_watch, ["forwarder", "forward-tetragon-events", "--tetragon-events-file", str(tetragon_events_file)],
        env=FORWARDER_ENVIRONMENT)

    assert result.exit_code == 0, result.output
    assert received_record_counts == [(2, False)]
    assert "Skipped 1 line(s) that are not JSON objects" in result.output
    assert "1 accepted, 0 rejected, 0 duplicate" in result.output


def test_forward_tetragon_events_exits_with_an_error_when_delivery_fails(
        cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tetragon_events_file: Path) -> None:
    def failing_forward_tetragon_records(
            tetragon_records: list[JsonObject], identity_assigner: EventIdentityAssigner, event_buffer: EventBuffer,
            event_batch_sender: EventBatchSender, is_dry_run: bool) -> ForwardingResult:
        raise IngestionRequestError("Could not reach http://127.0.0.1:8000/v1/events")

    monkeypatch.setattr(forwarder_commands, "forward_tetragon_records", failing_forward_tetragon_records)

    result: Result = cli_runner.invoke(
        agent_watch, ["forwarder", "forward-tetragon-events", "--tetragon-events-file", str(tetragon_events_file)],
        env=FORWARDER_ENVIRONMENT)

    assert result.exit_code == 1
    assert "Delivery failed: Could not reach" in result.output


def test_forward_tetragon_events_exits_with_an_error_when_an_event_is_rejected(
        cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tetragon_events_file: Path) -> None:
    def rejecting_forward_tetragon_records(
            tetragon_records: list[JsonObject], identity_assigner: EventIdentityAssigner, event_buffer: EventBuffer,
            event_batch_sender: EventBatchSender, is_dry_run: bool) -> ForwardingResult:
        return build_forwarding_result([RejectedEvent(index=0, event_id="sha256:a", reason="bad")])

    monkeypatch.setattr(forwarder_commands, "forward_tetragon_records", rejecting_forward_tetragon_records)

    result: Result = cli_runner.invoke(
        agent_watch, ["forwarder", "forward-tetragon-events", "--tetragon-events-file", str(tetragon_events_file)],
        env=FORWARDER_ENVIRONMENT)

    assert result.exit_code == 1
    assert "0 accepted, 1 rejected" in result.output
