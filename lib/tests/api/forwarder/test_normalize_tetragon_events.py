import logging

import pytest
from doubles.forwarder_test_doubles import TetragonRecordLoader

from agent_watch.api.forwarder.models import MalformedSensorRecordError
from agent_watch.api.forwarder.normalize_tetragon_events import (
    build_process_fields, build_v1_event, file_operation_name, first_argument_value, first_object_argument,
    kprobe_outcome, network_target, normalize_file_access, normalize_network_connect, normalize_process_exec,
    normalize_tetragon_record, parse_tetragon_json_lines, permission_bits_from_mode_text, present_fields,
    require_object, require_text, valid_port)
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.schema_validator import SchemaValidator


def test_parse_tetragon_json_lines_keeps_objects_and_counts_malformed_lines() -> None:
    tetragon_json_lines: str = '{"process_exec": {}}\n\nnot json\n[1, 2]\n{"node_name": "host"}\n'

    tetragon_records, malformed_line_count = parse_tetragon_json_lines(tetragon_json_lines)

    assert tetragon_records == [{"process_exec": {}}, {"node_name": "host"}]
    assert malformed_line_count == 2


@pytest.mark.parametrize("fixture_name", ["process-exec", "file-access", "network-connect"])
def test_normalize_tetragon_record_produces_a_schema_valid_event_for_each_supported_type(
        fixture_name: str, load_tetragon_record: TetragonRecordLoader,
        telemetry_schema_validator: SchemaValidator) -> None:
    normalized_event: JsonObject | None = normalize_tetragon_record(load_tetragon_record(fixture_name))

    assert normalized_event is not None
    event_with_identity: JsonObject = {"event_id": "sha256:test", "forwarder_seq": 1, **normalized_event}
    assert telemetry_schema_validator.validation_errors(event_with_identity) == []


def test_normalize_tetragon_record_skips_an_unsupported_event_type(
        load_tetragon_record: TetragonRecordLoader) -> None:
    assert normalize_tetragon_record(load_tetragon_record("process-exit")) is None


def test_normalize_tetragon_record_skips_an_unsupported_kprobe(
        caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logging.getLogger("agent_watch"), "propagate", True)
    with caplog.at_level(logging.DEBUG, logger="agent_watch"):
        assert normalize_tetragon_record({"process_kprobe": {"function_name": "sys_ptrace"}}) is None

    assert "Skipping unsupported Tetragon kprobe: sys_ptrace" in caplog.text


def test_normalize_process_exec_maps_the_program_and_its_parent(load_tetragon_record: TetragonRecordLoader) -> None:
    normalized_event: JsonObject = normalize_process_exec(load_tetragon_record("process-exec"))

    assert normalized_event["target"] == "/usr/bin/curl"
    assert normalized_event["details"]["parent_executable"] == "/bin/bash"
    assert normalized_event["agent"] == {"attribution_status": "unknown", "session_id": None}


def test_normalize_process_exec_rejects_a_record_without_a_binary() -> None:
    with pytest.raises(MalformedSensorRecordError):
        normalize_process_exec({"process_exec": {"process": {}}, "node_name": "host", "time": "2026-11-18T12:00:00Z"})


def test_normalize_file_access_maps_path_operation_and_permission(load_tetragon_record: TetragonRecordLoader) -> None:
    normalized_event: JsonObject = normalize_file_access(load_tetragon_record("file-access"))

    assert normalized_event["details"] == {
        "path": "/home/agent/decoy/credentials.txt", "operation": "read", "permission": 420}


def test_normalize_network_connect_maps_the_destination(load_tetragon_record: TetragonRecordLoader) -> None:
    normalized_event: JsonObject = normalize_network_connect(load_tetragon_record("network-connect"))

    assert normalized_event["target"] == "127.0.0.1:8080"
    assert normalized_event["details"]["protocol"] == "tcp"
    assert normalized_event["details"]["family"] == "ipv4"


@pytest.mark.parametrize("tetragon_record", [
    {"process_kprobe": "x"}, {"process_exec": []}, {"process_exec": {"process": "x"}},
    {"process_kprobe": {"function_name": "tcp_connect", "args": [{"sock_arg": {"daddr": "10.0.0.5"}}], "return": 0}},
], ids=["kprobe-text", "exec-list", "process-text", "return-number"])
def test_normalize_tetragon_record_rejects_a_container_that_is_not_an_object(tetragon_record: JsonObject) -> None:
    with pytest.raises(MalformedSensorRecordError, match="is not an object"):
        normalize_tetragon_record(tetragon_record)


def test_build_v1_event_sets_the_fixed_contract_fields() -> None:
    event: JsonObject = build_v1_event({"time": "2026-11-18T12:00:00Z", "node_name": "host"}, "process_exec", {},
                                       target="/bin/ls", outcome="success", details={})

    assert (event["schema_version"], event["source"], event["host"]) == ("1.0", "tetragon", "host")
    assert event["agent"] == {"attribution_status": "unknown", "session_id": None}


@pytest.mark.parametrize("missing_field_name", ["time", "node_name"])
def test_build_v1_event_rejects_a_record_without_time_or_host(missing_field_name: str) -> None:
    tetragon_record: JsonObject = {"time": "2026-11-18T12:00:00Z", "node_name": "host"}
    del tetragon_record[missing_field_name]

    with pytest.raises(MalformedSensorRecordError, match=missing_field_name):
        build_v1_event(tetragon_record, "process_exec", {}, target="/bin/ls", outcome="success", details={})


def test_require_object_treats_a_missing_field_as_empty() -> None:
    assert require_object({}, "parent") == {}


def test_build_process_fields_omits_fields_the_sensor_did_not_provide() -> None:
    assert build_process_fields({"pid": 10, "binary": "/bin/ls"}, {}) == {"pid": 10, "executable": "/bin/ls"}


def test_present_fields_drops_missing_and_empty_values() -> None:
    assert present_fields({"kept": 0, "missing": None, "empty": ""}) == {"kept": 0}


def test_require_text_rejects_a_missing_field() -> None:
    with pytest.raises(MalformedSensorRecordError, match="node_name"):
        require_text({}, "node_name")


def test_first_argument_value_returns_the_first_matching_argument() -> None:
    kprobe: JsonObject = {"args": [{"file_arg": {"path": "/a"}}, {"int_arg": 4}, {"int_arg": 2}]}

    assert first_argument_value(kprobe, "int_arg") == 4
    assert first_argument_value(kprobe, "sock_arg") is None


def test_first_object_argument_returns_an_empty_object_when_absent() -> None:
    assert first_object_argument({"args": [{"int_arg": 4}]}, "file_arg") == {}


def test_first_argument_value_skips_arguments_that_are_not_objects() -> None:
    assert first_argument_value({"args": ["int_arg", {"int_arg": 4}]}, "int_arg") == 4
    assert first_argument_value({"args": "int_arg"}, "int_arg") is None


@pytest.mark.parametrize(("function_name", "access_mask", "expected_operation"), [
    ("security_file_permission", 4, "read"),
    ("security_file_permission", 2, "write"),
    ("security_file_permission", 6, "read_write"),
    ("security_file_permission", 1, None),
    ("security_file_permission", None, None),
    ("security_file_open", 4, "open"),
    ("security_file_open", None, "open"),
], ids=["read", "write", "read-write", "execute-only", "no-mask", "open-hook", "open-hook-no-mask"])
def test_file_operation_name(function_name: str, access_mask: int | None, expected_operation: str | None) -> None:
    assert file_operation_name(function_name, access_mask) == expected_operation


@pytest.mark.parametrize(("mode_text", "expected_permission"), [
    ("-rw-r--r--", 0o644), ("-rwxr-xr-x", 0o755), ("-rwsr-xr-x", 0o4755), ("-rwxr-sr-x", 0o2755),
    ("drwxrwxrwt", 0o1777), ("-rwSr-xr-T", 0o5654), ("rw-", None), (None, None),
], ids=["0644", "0755", "setuid", "setgid", "sticky", "special-bits-without-execute", "too-short", "missing"])
def test_permission_bits_from_mode_text(mode_text: str | None, expected_permission: int | None) -> None:
    assert permission_bits_from_mode_text(mode_text) == expected_permission


@pytest.mark.parametrize(("kprobe", "expected_outcome"), [
    ({"return": {"int_arg": 0}}, "success"),
    ({"return": {"int_arg": -13}}, "denied"),
    ({"return": {"int_arg": -1}}, "denied"),
    ({"return": {"int_arg": -2}}, "unknown"),
    ({}, "unknown"),
], ids=["zero", "access-denied", "not-permitted", "other-error", "no-return-value"])
def test_kprobe_outcome(kprobe: JsonObject, expected_outcome: str) -> None:
    assert kprobe_outcome(kprobe) == expected_outcome


@pytest.mark.parametrize(("port", "expected_port"), [(443, 443), (0, None), (70000, None), ("443", None)],
                         ids=["valid", "zero", "too-large", "text"])
def test_valid_port(port: object, expected_port: int | None) -> None:
    assert valid_port(port) == expected_port


@pytest.mark.parametrize(("destination_port", "family", "expected_target"), [
    (443, "ipv4", "10.0.0.5:443"), (443, "ipv6", "[10.0.0.5]:443"), (None, "ipv4", "10.0.0.5"),
], ids=["ipv4", "ipv6", "no-port"])
def test_network_target(destination_port: int | None, family: str, expected_target: str) -> None:
    assert network_target("10.0.0.5", destination_port, family) == expected_target
