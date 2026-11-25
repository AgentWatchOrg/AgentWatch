import urllib.request

import pytest
from doubles.splunk_export_test_doubles import (
    TEST_HEC_TOKEN, RecordingHecEventSender, ScriptedHecUrlopen, SplunkHecSettingsFactory)

from agent_watch.api.splunk_export.models import SplunkHecSettings


@pytest.fixture
def make_hec_settings() -> SplunkHecSettingsFactory:
    def build_hec_settings(hec_url: str = "https://splunk.invalid:8088", index: str | None = None,
                           should_verify_tls: bool = True) -> SplunkHecSettings:
        return SplunkHecSettings(hec_url=hec_url, hec_token=TEST_HEC_TOKEN, index=index,
                                 should_verify_tls=should_verify_tls)
    return build_hec_settings


@pytest.fixture
def scripted_hec_urlopen(monkeypatch: pytest.MonkeyPatch) -> ScriptedHecUrlopen:
    fake_urlopen: ScriptedHecUrlopen = ScriptedHecUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return fake_urlopen


@pytest.fixture
def recording_hec_event_sender() -> RecordingHecEventSender:
    return RecordingHecEventSender()
