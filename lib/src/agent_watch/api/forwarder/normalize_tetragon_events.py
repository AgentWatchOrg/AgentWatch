import json
import logging
from typing import Any

from agent_watch.api.forwarder.models import TELEMETRY_SCHEMA_VERSION, TETRAGON_SOURCE_NAME, MalformedSensorRecordError
from agent_watch.api.github_client import JsonObject

FILE_ACCESS_FUNCTION_NAMES: frozenset[str] = frozenset({"security_file_permission", "security_file_open"})
NETWORK_CONNECT_FUNCTION_NAMES: frozenset[str] = frozenset({"tcp_connect"})
LINUX_MAY_WRITE_MASK: int = 0x2
LINUX_MAY_READ_MASK: int = 0x4
PERMISSION_BIT_VALUES: list[int] = [0o400, 0o200, 0o100, 0o040, 0o020, 0o010, 0o004, 0o002, 0o001]
SPECIAL_PERMISSION_BITS: list[tuple[int, str, int]] = [(3, "sS", 0o4000), (6, "sS", 0o2000), (9, "tT", 0o1000)]
ADDRESS_FAMILY_NAMES: dict[str, str] = {"AF_INET": "ipv4", "AF_INET6": "ipv6"}
TRANSPORT_PROTOCOL_NAMES: dict[str, str] = {"IPPROTO_TCP": "tcp", "IPPROTO_UDP": "udp"}
PERMISSION_DENIED_RETURN_VALUES: frozenset[int] = frozenset({-1, -13})

logger: logging.Logger = logging.getLogger(__name__)


def parse_tetragon_json_lines(tetragon_json_lines: str) -> tuple[list[JsonObject], int]:
    tetragon_records: list[JsonObject] = []
    malformed_line_count: int = 0
    for line in tetragon_json_lines.split("\n"):
        if not line.strip():
            continue
        try:
            parsed_line: Any = json.loads(line)
        except json.JSONDecodeError:
            parsed_line = None
        if isinstance(parsed_line, dict):
            tetragon_records.append(parsed_line)
        else:
            logger.debug("Skipping a Tetragon line that is not a JSON object")
            malformed_line_count += 1
    return tetragon_records, malformed_line_count


def normalize_tetragon_record(tetragon_record: JsonObject) -> JsonObject | None:
    if "process_exec" in tetragon_record:
        return normalize_process_exec(tetragon_record)
    if "process_kprobe" not in tetragon_record:
        logger.debug("Skipping unsupported Tetragon record type: %s", ", ".join(sorted(tetragon_record)))
        return None
    function_name: str = str(require_object(tetragon_record, "process_kprobe").get("function_name", ""))
    if function_name in FILE_ACCESS_FUNCTION_NAMES:
        return normalize_file_access(tetragon_record)
    if function_name in NETWORK_CONNECT_FUNCTION_NAMES:
        return normalize_network_connect(tetragon_record)
    logger.debug("Skipping unsupported Tetragon kprobe: %s", function_name)
    return None


def normalize_process_exec(tetragon_record: JsonObject) -> JsonObject:
    process_exec: JsonObject = require_object(tetragon_record, "process_exec")
    tetragon_process: JsonObject = require_object(process_exec, "process")
    tetragon_parent: JsonObject = require_object(process_exec, "parent")
    executable: str = require_text(tetragon_process, "binary")
    details: JsonObject = present_fields({
        "arguments": tetragon_process.get("arguments"),
        "cwd": tetragon_process.get("cwd"),
        "parent_executable": tetragon_parent.get("binary"),
    })
    return build_v1_event(tetragon_record, "process_exec", build_process_fields(tetragon_process, tetragon_parent),
                          target=executable, outcome="success", details=details)


def normalize_file_access(tetragon_record: JsonObject) -> JsonObject:
    kprobe: JsonObject = require_object(tetragon_record, "process_kprobe")
    file_argument: JsonObject = first_object_argument(kprobe, "file_arg")
    path: str = require_text(file_argument, "path")
    access_mask: Any = first_argument_value(kprobe, "int_arg")
    details: JsonObject = present_fields({
        "path": path,
        "operation": file_operation_name(kprobe["function_name"], access_mask),
        "permission": permission_bits_from_mode_text(file_argument.get("permission")),
    })
    return build_v1_event(tetragon_record, "file_access",
                          build_process_fields(require_object(kprobe, "process"), require_object(kprobe, "parent")),
                          target=path, outcome=kprobe_outcome(kprobe), details=details)


def normalize_network_connect(tetragon_record: JsonObject) -> JsonObject:
    kprobe: JsonObject = require_object(tetragon_record, "process_kprobe")
    socket_argument: JsonObject = first_object_argument(kprobe, "sock_arg")
    destination_address: str = require_text(socket_argument, "daddr")
    destination_port: int | None = valid_port(socket_argument.get("dport"))
    family: str | None = ADDRESS_FAMILY_NAMES.get(socket_argument.get("family", ""))
    details: JsonObject = present_fields({
        "protocol": TRANSPORT_PROTOCOL_NAMES.get(socket_argument.get("protocol", "")),
        "family": family,
        "src_addr": socket_argument.get("saddr") or None,
        "src_port": valid_port(socket_argument.get("sport")),
        "dst_addr": destination_address,
        "dst_port": destination_port,
    })
    return build_v1_event(tetragon_record, "network_connect",
                          build_process_fields(require_object(kprobe, "process"), require_object(kprobe, "parent")),
                          target=network_target(destination_address, destination_port, family),
                          outcome=kprobe_outcome(kprobe), details=details)


def build_v1_event(tetragon_record: JsonObject, activity_type: str, process_fields: JsonObject, target: str,
                   outcome: str, details: JsonObject) -> JsonObject:
    return {
        "schema_version": TELEMETRY_SCHEMA_VERSION,
        "timestamp": require_text(tetragon_record, "time"),
        "host": require_text(tetragon_record, "node_name"),
        "source": TETRAGON_SOURCE_NAME,
        "activity_type": activity_type,
        "process": process_fields,
        "agent": {"attribution_status": "unknown", "session_id": None},
        "target": target,
        "outcome": outcome,
        "details": details,
    }


def build_process_fields(tetragon_process: JsonObject, tetragon_parent: JsonObject) -> JsonObject:
    return present_fields({
        "exec_id": tetragon_process.get("exec_id"),
        "parent_exec_id": tetragon_process.get("parent_exec_id"),
        "pid": tetragon_process.get("pid"),
        "ppid": tetragon_parent.get("pid"),
        "executable": tetragon_process.get("binary"),
        "user_id": tetragon_process.get("uid"),
    })


def present_fields(candidate_fields: JsonObject) -> JsonObject:
    return {name: value for name, value in candidate_fields.items() if value is not None and value != ""}


def require_text(container: JsonObject, field_name: str) -> str:
    value: object = container.get(field_name)
    if not isinstance(value, str) or not value:
        raise MalformedSensorRecordError(f"Tetragon record has no {field_name}")
    return value


def require_object(container: JsonObject, field_name: str) -> JsonObject:
    value: object = container.get(field_name, {})
    if not isinstance(value, dict):
        raise MalformedSensorRecordError(f"Tetragon field {field_name} is not an object")
    return value


def first_argument_value(kprobe: JsonObject, argument_kind: str) -> Any:
    kprobe_arguments: object = kprobe.get("args")
    for argument in kprobe_arguments if isinstance(kprobe_arguments, list) else []:
        if isinstance(argument, dict) and argument_kind in argument:
            return argument[argument_kind]
    return None


def first_object_argument(kprobe: JsonObject, argument_kind: str) -> JsonObject:
    argument_value: Any = first_argument_value(kprobe, argument_kind)
    return argument_value if isinstance(argument_value, dict) else {}


def file_operation_name(function_name: str, access_mask: object) -> str | None:
    if function_name == "security_file_open":
        return "open"
    if not isinstance(access_mask, int):
        return None
    is_read: bool = bool(access_mask & LINUX_MAY_READ_MASK)
    is_write: bool = bool(access_mask & LINUX_MAY_WRITE_MASK)
    if is_read and is_write:
        return "read_write"
    if is_write:
        return "write"
    return "read" if is_read else None


def permission_bits_from_mode_text(mode_text: str | None) -> int | None:
    if not mode_text or len(mode_text) != 10:
        return None
    access_bits: int = sum(bit_value for bit_value, mode_character in zip(PERMISSION_BIT_VALUES, mode_text[1:])
                           if mode_character not in "-ST")
    special_bits: int = sum(bit_value for position, mode_characters, bit_value in SPECIAL_PERMISSION_BITS
                            if mode_text[position] in mode_characters)
    return access_bits + special_bits


def kprobe_outcome(kprobe: JsonObject) -> str:
    return_value: object = require_object(kprobe, "return").get("int_arg")
    if not isinstance(return_value, int):
        return "unknown"
    if return_value >= 0:
        return "success"
    return "denied" if return_value in PERMISSION_DENIED_RETURN_VALUES else "unknown"


def valid_port(port: object) -> int | None:
    return port if isinstance(port, int) and 1 <= port <= 65535 else None


def network_target(destination_address: str, destination_port: int | None, family: str | None) -> str:
    if destination_port is None:
        return destination_address
    if family == "ipv6":
        return f"[{destination_address}]:{destination_port}"
    return f"{destination_address}:{destination_port}"
