import http.client
import ssl
import urllib.error
import urllib.request

import pytest
from doubles.splunk_export_test_doubles import (
    FAKE_HEC_EVENT_URL, TEST_HEC_TOKEN, ScriptedHecUrlopen, SplunkHecSettingsFactory, build_hec_http_error,
    parse_concatenated_hec_events)

from agent_watch.api.splunk_export.models import SplunkExportError
from agent_watch.api.splunk_export.splunk_hec_client import SplunkHecClient


@pytest.fixture
def hec_client(make_hec_settings: SplunkHecSettingsFactory) -> SplunkHecClient:
    return SplunkHecClient(make_hec_settings())


def test_send_hec_events_posts_concatenated_events_with_the_token(
        hec_client: SplunkHecClient, scripted_hec_urlopen: ScriptedHecUrlopen) -> None:
    hec_client.send_hec_events([{"event": {"event_id": "a"}}, {"event": {"event_id": "b"}}])

    sent_request: urllib.request.Request = scripted_hec_urlopen.sent_requests[0]
    assert sent_request.full_url == FAKE_HEC_EVENT_URL
    assert sent_request.get_header("Authorization") == f"Splunk {TEST_HEC_TOKEN}"
    assert isinstance(sent_request.data, bytes)
    assert parse_concatenated_hec_events(sent_request.data) == [
        {"event": {"event_id": "a"}}, {"event": {"event_id": "b"}}]


def test_send_hec_events_reports_a_retryable_rejection_without_revealing_the_token(
        hec_client: SplunkHecClient, scripted_hec_urlopen: ScriptedHecUrlopen) -> None:
    scripted_hec_urlopen.failure = build_hec_http_error(403, '{"text":"Invalid token","code":4}')

    with pytest.raises(SplunkExportError, match="HTTP 403: .*Invalid token") as raised_error:
        hec_client.send_hec_events([{"event": {"event_id": "a"}}])

    assert TEST_HEC_TOKEN not in str(raised_error.value)
    assert raised_error.value.is_retryable is True


@pytest.mark.parametrize("permanent_status", [400, 413])
def test_send_hec_events_marks_bad_data_and_oversized_rejections_as_permanent(
        permanent_status: int, hec_client: SplunkHecClient, scripted_hec_urlopen: ScriptedHecUrlopen) -> None:
    scripted_hec_urlopen.failure = build_hec_http_error(permanent_status, '{"text":"Rejected","code":6}')

    with pytest.raises(SplunkExportError) as raised_error:
        hec_client.send_hec_events([{"event": {"event_id": "a"}}])

    assert raised_error.value.is_retryable is False


@pytest.mark.parametrize("connection_failure", [
    urllib.error.URLError("[Errno 111] Connection refused"),
    http.client.RemoteDisconnected("Remote end closed connection without response"),
    TimeoutError("timed out"),
], ids=["unreachable", "dropped-before-response", "timeout"])
def test_send_hec_events_reports_a_connection_failure_as_retryable(
        connection_failure: Exception, hec_client: SplunkHecClient,
        scripted_hec_urlopen: ScriptedHecUrlopen) -> None:
    scripted_hec_urlopen.failure = connection_failure

    with pytest.raises(SplunkExportError, match="Could not reach Splunk HEC") as raised_error:
        hec_client.send_hec_events([{"event": {"event_id": "a"}}])

    assert TEST_HEC_TOKEN not in str(raised_error.value)
    assert raised_error.value.is_retryable is True


def test_splunk_hec_client_builds_the_event_url_from_a_base_url_with_a_trailing_slash(
        make_hec_settings: SplunkHecSettingsFactory) -> None:
    hec_client: SplunkHecClient = SplunkHecClient(make_hec_settings("https://localhost:8088/"))

    assert hec_client.events_url == "https://localhost:8088/services/collector/event"


@pytest.mark.parametrize(("should_verify_tls", "expected_verify_mode"), [
    (True, ssl.CERT_REQUIRED), (False, ssl.CERT_NONE)], ids=["verify", "skip-verification"])
def test_splunk_hec_client_checks_certificates_unless_told_not_to(
        should_verify_tls: bool, expected_verify_mode: ssl.VerifyMode,
        make_hec_settings: SplunkHecSettingsFactory) -> None:
    hec_client: SplunkHecClient = SplunkHecClient(make_hec_settings(should_verify_tls=should_verify_tls))

    assert hec_client._tls_context.verify_mode == expected_verify_mode
    assert hec_client._tls_context.check_hostname is should_verify_tls
