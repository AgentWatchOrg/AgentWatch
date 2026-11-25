from dataclasses import dataclass

HEC_EVENT_PATH: str = "/services/collector/event"
PERMANENT_REJECTION_STATUS_CODES: frozenset[int] = frozenset({400, 413})


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

