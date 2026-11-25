import ssl

import pytest
from doubles.splunk_export_test_doubles import (
    TEST_HEC_TOKEN, FakeSplunkHecServer, ReceivedHecRequest, SplunkHecSettingsFactory, parse_concatenated_hec_events)

from agent_watch.api.splunk_export.models import SplunkExportError, SplunkHecSettings
from agent_watch.api.splunk_export.splunk_hec_client import SplunkHecClient


def test_send_hec_events_posts_concatenated_events_with_the_token(
        fake_splunk_hec_server: FakeSplunkHecServer, make_hec_settings: SplunkHecSettingsFactory) -> None:
    hec_client: SplunkHecClient = SplunkHecClient(make_hec_settings(fake_splunk_hec_server.url))

    hec_client.send_hec_events([{"event": {"event_id": "a"}}, {"event": {"event_id": "b"}}])

    received_request: ReceivedHecRequest = fake_splunk_hec_server.received_requests[0]
    assert received_request.path == "/services/collector/event"
    assert received_request.authorization == f"Splunk {TEST_HEC_TOKEN}"
    assert parse_concatenated_hec_events(received_request.body) == [
        {"event": {"event_id": "a"}}, {"event": {"event_id": "b"}}]


def test_send_hec_events_reports_a_rejection_without_revealing_the_token(
        fake_splunk_hec_server: FakeSplunkHecServer, make_hec_settings: SplunkHecSettingsFactory) -> None:
    fake_splunk_hec_server.response_status = 403
    fake_splunk_hec_server.response_body = '{"text":"Invalid token","code":4}'
    hec_client: SplunkHecClient = SplunkHecClient(make_hec_settings(fake_splunk_hec_server.url))

    with pytest.raises(SplunkExportError, match="HTTP 403: .*Invalid token") as raised_error:
        hec_client.send_hec_events([{"event": {"event_id": "a"}}])

    assert TEST_HEC_TOKEN not in str(raised_error.value)
    assert raised_error.value.is_retryable is True


@pytest.mark.parametrize("permanent_status", [400, 413])
def test_send_hec_events_marks_bad_data_and_oversized_rejections_as_permanent(
        permanent_status: int, fake_splunk_hec_server: FakeSplunkHecServer,
        make_hec_settings: SplunkHecSettingsFactory) -> None:
    fake_splunk_hec_server.response_status = permanent_status
    hec_client: SplunkHecClient = SplunkHecClient(make_hec_settings(fake_splunk_hec_server.url))

    with pytest.raises(SplunkExportError) as raised_error:
        hec_client.send_hec_events([{"event": {"event_id": "a"}}])

    assert raised_error.value.is_retryable is False


def test_send_hec_events_reports_an_unreachable_endpoint(
        unused_local_url: str, make_hec_settings: SplunkHecSettingsFactory) -> None:
    hec_client: SplunkHecClient = SplunkHecClient(make_hec_settings(unused_local_url), request_timeout_seconds=2)

    with pytest.raises(SplunkExportError, match="Could not reach Splunk HEC") as raised_error:
        hec_client.send_hec_events([{"event": {"event_id": "a"}}])

    assert TEST_HEC_TOKEN not in str(raised_error.value)


def test_send_hec_events_reports_a_connection_dropped_before_the_response(
        fake_splunk_hec_server: FakeSplunkHecServer, make_hec_settings: SplunkHecSettingsFactory) -> None:
    fake_splunk_hec_server.should_drop_connection = True
    hec_client: SplunkHecClient = SplunkHecClient(make_hec_settings(fake_splunk_hec_server.url))

    with pytest.raises(SplunkExportError, match="Could not reach Splunk HEC") as raised_error:
        hec_client.send_hec_events([{"event": {"event_id": "a"}}])

    assert TEST_HEC_TOKEN not in str(raised_error.value)


def test_splunk_hec_client_builds_the_event_url_from_a_base_url_with_a_trailing_slash(
        make_hec_settings: SplunkHecSettingsFactory) -> None:
    hec_client: SplunkHecClient = SplunkHecClient(make_hec_settings("https://localhost:8088/"))

    assert hec_client.events_url == "https://localhost:8088/services/collector/event"


def test_splunk_hec_client_skips_certificate_checks_only_when_asked() -> None:
    unverified_client: SplunkHecClient = SplunkHecClient(SplunkHecSettings(
        hec_url="https://localhost:8088", hec_token=TEST_HEC_TOKEN, index=None, should_verify_tls=False))

    assert unverified_client._tls_context.verify_mode == ssl.CERT_NONE
