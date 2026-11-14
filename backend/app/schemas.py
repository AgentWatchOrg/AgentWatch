"""
AgentWatch v1 telemetry event schema (DRAFT, spike prototype).

Covers the sensor -> forwarder -> backend hop only. Field choices follow the
candidate fields named in the design roadmap (Section 7.3): event id,
timestamp, host, agent session, process lineage, action type, target,
outcome. This is intentionally minimal — just enough to unblock the
ingestion-interface spike (#7). Finalizing this schema is the scope of
spike #6; treat the shapes below as a starting proposal, not a contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


SCHEMA_VERSION = "1.0"

ActivityType = Literal["process_exec", "file_access", "network_connect"]
SensorSource = Literal["tetragon", "auditd"]
Outcome = Literal["success", "failure", "unknown"]


class ProcessInfo(BaseModel):
    """Process-lineage fields used to attribute an event to an agent session."""

    pid: int
    ppid: Optional[int] = None
    exec_id: Optional[str] = Field(
        default=None,
        description="Sensor-provided unique execution id (e.g. Tetragon exec_id), if available.",
    )
    binary_path: Optional[str] = None
    process_name: Optional[str] = None


class ProcessExecDetails(BaseModel):
    activity_type: Literal["process_exec"] = "process_exec"
    binary: str
    args: List[str] = Field(default_factory=list)
    cwd: Optional[str] = None


class FileAccessDetails(BaseModel):
    activity_type: Literal["file_access"] = "file_access"
    path: str
    access_mode: Literal["read", "write", "read_write"]


class NetworkConnectDetails(BaseModel):
    activity_type: Literal["network_connect"] = "network_connect"
    dest_ip: str
    dest_port: int
    protocol: Literal["tcp", "udp"] = "tcp"


ActivityDetails = Union[ProcessExecDetails, FileAccessDetails, NetworkConnectDetails]


class TelemetryEvent(BaseModel):
    """A single normalized telemetry event submitted by the forwarder."""

    event_id: str = Field(..., description="Forwarder-generated UUID; used for de-duplication.")
    schema_version: str = SCHEMA_VERSION
    timestamp: datetime = Field(..., description="UTC time the activity occurred (not ingestion time).")
    host: str
    agent_session_id: str = Field(
        ..., description="Correlation id for the monitored agent session (see spike #5)."
    )
    source: SensorSource
    process: ProcessInfo
    activity_type: ActivityType
    details: ActivityDetails
    outcome: Outcome = "unknown"

    def coherence_errors(self) -> List[str]:
        """Extra cross-field checks pydantic's type system alone can't express."""
        errors: List[str] = []
        if self.activity_type != self.details.activity_type:
            errors.append(
                f"activity_type '{self.activity_type}' does not match "
                f"details.activity_type '{self.details.activity_type}'"
            )
        return errors


class EventBatch(BaseModel):
    events: List[TelemetryEvent]


class RejectedEvent(BaseModel):
    index: int
    event_id: Optional[str] = None
    reason: str


class IngestResult(BaseModel):
    accepted: int
    rejected: List[RejectedEvent]
    duplicate: List[RejectedEvent]
