from dataclasses import dataclass

TELEMETRY_SOURCETYPE: str = "agentwatch:telemetry"
TELEMETRY_SOURCE: str = "agentwatch:ingestion"
HEC_EVENT_PATH: str = "/services/collector/event"


class SplunkExportError(Exception):
    def __init__(self, message: str, is_retryable: bool = True) -> None:
        super().__init__(message)
        self.is_retryable: bool = is_retryable


@dataclass(frozen=True)
class SplunkHecSettings:
    hec_url: str
    hec_token: str
    index: str | None
    should_verify_tls: bool


@dataclass
class HecExportProgress:
    sent_event_count: int = 0
    dropped_event_count: int = 0


@dataclass(frozen=True)
class ExportResult:
    exported_event_count: int
    dropped_event_count: int
    failed_event_count: int
