from dataclasses import dataclass

TELEMETRY_SOURCETYPE: str = "agentwatch:telemetry"
TELEMETRY_SOURCE: str = "agentwatch:ingestion"
HEC_EVENT_PATH: str = "/services/collector/event"


class SplunkExportError(Exception):
    pass


@dataclass(frozen=True)
class SplunkHecSettings:
    hec_url: str
    hec_token: str
    index: str | None
    should_verify_tls: bool


@dataclass(frozen=True)
class ExportResult:
    exported_event_count: int
    failed_event_count: int
