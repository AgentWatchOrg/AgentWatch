from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from doubles.forwarder_test_doubles import ForwardingResultFactory
from telemetry_fixture_paths import TETRAGON_RAW_FIXTURE_DIRECTORY

from agent_watch.api.forwarder.assign_event_identities import EventIdentityAssigner
from agent_watch.api.forwarder.event_buffer import EventBuffer
from agent_watch.api.forwarder.forward_events import EventBatchSender
from agent_watch.api.forwarder.models import ForwardingResult, IngestionRequestError
from agent_watch.api.ingestion.models import RejectedEvent
from agent_watch.cli import forwarder_commands
from agent_watch.cli.main import agent_watch

FORWARDER_ENVIRONMENT: dict[str, str] = {"INGESTION_URL": "http://127.0.0.1:8000", "INGESTION_API_KEY": "key"}
NO_INGESTION_ENVIRONMENT: dict[str, str | None] = {"INGESTION_URL": None, "INGESTION_API_KEY": None}


@pytest.fixture
def tetragon_events_file(tmp_path: Path) -> Path:
    raw_record_lines: list[str] = [
        (TETRAGON_RAW_FIXTURE_DIRECTORY / f"{fixture_name}.json").read_text(encoding="utf-8").replace("\n", "")
        for fixture_name in ["process-exec", "process-exit"]]
    events_file: Path = tmp_path / "tetragon-events.json"
    events_file.write_text("\n".join(raw_record_lines + ["not json"]) + "\n", encoding="utf-8")
    return events_file


@pytest.fixture
def make_forwarding_result() -> ForwardingResultFactory:
    def build_forwarding_result(rejected_events: list[RejectedEvent]) -> ForwardingResult:
        return ForwardingResult(planned_event_count=1, skipped_record_count=1,
                                accepted_count=1 - len(rejected_events), rejected_events=rejected_events,
                                duplicate_events=[], unsent_event_count=0, malformed_line_count=1)
    return build_forwarding_result


@pytest.fixture
def rejected_event() -> RejectedEvent:
    return RejectedEvent(index=0, event_id="sha256:a", reason="bad")


def test_forward_tetragon_events_reports_the_delivery(
        cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tetragon_events_file: Path,
        make_forwarding_result: ForwardingResultFactory) -> None:
    received_exports: list[tuple[str, bool]] = []

    def fake_forward_tetragon_export(
            tetragon_json_lines: str, identity_assigner: EventIdentityAssigner, event_buffer: EventBuffer,
            event_batch_sender: EventBatchSender | None, is_dry_run: bool) -> ForwardingResult:
        received_exports.append((tetragon_json_lines, is_dry_run))
        return make_forwarding_result([])

    monkeypatch.setattr(forwarder_commands, "forward_tetragon_export", fake_forward_tetragon_export)

    result: Result = cli_runner.invoke(
        agent_watch, ["forwarder", "forward-tetragon-events", "--tetragon-events-file", str(tetragon_events_file)],
        env=FORWARDER_ENVIRONMENT)

    assert result.exit_code == 0, result.output
    assert received_exports == [(tetragon_events_file.read_text(encoding="utf-8"), False)]
    assert "Skipped 1 line(s) that are not JSON objects" in result.output
    assert "1 accepted, 0 rejected, 0 duplicate" in result.output


def test_forward_tetragon_events_exits_with_an_error_when_delivery_fails(
        cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tetragon_events_file: Path) -> None:
    def failing_forward_tetragon_export(
            tetragon_json_lines: str, identity_assigner: EventIdentityAssigner, event_buffer: EventBuffer,
            event_batch_sender: EventBatchSender | None, is_dry_run: bool) -> ForwardingResult:
        raise IngestionRequestError("Could not reach http://127.0.0.1:8000/v1/events")

    monkeypatch.setattr(forwarder_commands, "forward_tetragon_export", failing_forward_tetragon_export)

    result: Result = cli_runner.invoke(
        agent_watch, ["forwarder", "forward-tetragon-events", "--tetragon-events-file", str(tetragon_events_file)],
        env=FORWARDER_ENVIRONMENT)

    assert result.exit_code == 1
    assert "Delivery failed: Could not reach" in result.output


def test_forward_tetragon_events_exits_with_an_error_when_an_event_is_rejected(
        cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tetragon_events_file: Path,
        make_forwarding_result: ForwardingResultFactory, rejected_event: RejectedEvent) -> None:
    def rejecting_forward_tetragon_export(
            tetragon_json_lines: str, identity_assigner: EventIdentityAssigner, event_buffer: EventBuffer,
            event_batch_sender: EventBatchSender | None, is_dry_run: bool) -> ForwardingResult:
        return make_forwarding_result([rejected_event])

    monkeypatch.setattr(forwarder_commands, "forward_tetragon_export", rejecting_forward_tetragon_export)

    result: Result = cli_runner.invoke(
        agent_watch, ["forwarder", "forward-tetragon-events", "--tetragon-events-file", str(tetragon_events_file)],
        env=FORWARDER_ENVIRONMENT)

    assert result.exit_code == 1
    assert "0 accepted, 1 rejected" in result.output


def test_forward_tetragon_events_dry_run_plans_without_reporting_a_delivery(
        cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tetragon_events_file: Path,
        make_forwarding_result: ForwardingResultFactory) -> None:
    received_dry_run_flags: list[bool] = []

    def recording_forward_tetragon_export(
            tetragon_json_lines: str, identity_assigner: EventIdentityAssigner, event_buffer: EventBuffer,
            event_batch_sender: EventBatchSender | None, is_dry_run: bool) -> ForwardingResult:
        received_dry_run_flags.append(is_dry_run and event_batch_sender is None)
        return make_forwarding_result([])

    monkeypatch.setattr(forwarder_commands, "forward_tetragon_export", recording_forward_tetragon_export)

    result: Result = cli_runner.invoke(agent_watch, [
        "forwarder", "forward-tetragon-events", "--tetragon-events-file", str(tetragon_events_file), "--dry-run"],
        env=NO_INGESTION_ENVIRONMENT)

    assert result.exit_code == 0, result.output
    assert received_dry_run_flags == [True]
    assert "1 event(s) planned, 1 record(s) skipped (dry run)" in result.output
    assert "accepted" not in result.output


def test_forward_tetragon_events_requires_ingestion_settings_unless_it_is_a_dry_run(
        cli_runner: CliRunner, tetragon_events_file: Path) -> None:
    result: Result = cli_runner.invoke(
        agent_watch, ["forwarder", "forward-tetragon-events", "--tetragon-events-file", str(tetragon_events_file)],
        env=NO_INGESTION_ENVIRONMENT)

    assert result.exit_code == 2
    assert "--ingestion-url and --ingestion-api-key are required unless --dry-run is set" in result.output
