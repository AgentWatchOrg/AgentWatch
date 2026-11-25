import socket
from typing import Iterator

import pytest
from doubles.splunk_export_test_doubles import (
    TEST_HEC_TOKEN, FakeSplunkHecServer, SplunkHecSettingsFactory, start_fake_splunk_hec_server)

from agent_watch.api.splunk_export.models import SplunkHecSettings


@pytest.fixture
def make_hec_settings() -> SplunkHecSettingsFactory:
    def build_hec_settings(hec_url: str, index: str | None = None) -> SplunkHecSettings:
        return SplunkHecSettings(hec_url=hec_url, hec_token=TEST_HEC_TOKEN, index=index, should_verify_tls=True)
    return build_hec_settings


@pytest.fixture
def fake_splunk_hec_server() -> Iterator[FakeSplunkHecServer]:
    fake_server_state, http_server = start_fake_splunk_hec_server()
    yield fake_server_state
    http_server.shutdown()
    http_server.server_close()


@pytest.fixture
def unused_local_url() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unused_socket:
        unused_socket.bind(("127.0.0.1", 0))
        unused_port: int = unused_socket.getsockname()[1]
    return f"http://127.0.0.1:{unused_port}"

