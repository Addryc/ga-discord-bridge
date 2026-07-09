"""GA4 client tests.

All network traffic is served by ``httpx.MockTransport`` from the recorded
API responses in ``tests/samples`` — no live credentials anywhere. The
drift-detection test is the important one: it pins the metric/dimension
names the client *sends* against the names in the recorded *responses*, so a
typo here or a rename upstream fails loudly instead of zero-filling.
"""

from __future__ import annotations

import json

import httpx
import pytest

from ga_discord_bridge.domain import DayTotals
from ga_discord_bridge.errors import (
    AnalyticsAuthError,
    AnalyticsResponseError,
    AnalyticsTransportError,
)
from ga_discord_bridge.ga4 import (
    Ga4Client,
    MetadataServerTokenProvider,
    ServiceAccountTokenProvider,
)
from tests.conftest import SAMPLE_DAY, load_sample, make_sample_digest

# Order in which fetch_daily_digest issues its runReport calls; each entry is
# the recorded sample whose headers are the drift oracle for that request.
FIXTURES_IN_REQUEST_ORDER = (
    "ga4_run_report_totals.json",
    "ga4_run_report_top_pages.json",
    "ga4_run_report_top_channels.json",
    "ga4_run_report_top_events.json",
)


def fixture_handler(requests_seen: list[httpx.Request]):
    """Serve the recorded runReport samples keyed on the requested dimension."""
    fixtures_by_dimension = {
        None: "ga4_run_report_totals.json",
        "pagePath": "ga4_run_report_top_pages.json",
        "sessionDefaultChannelGroup": "ga4_run_report_top_channels.json",
        "eventName": "ga4_run_report_top_events.json",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        body = json.loads(request.content.decode("utf-8"))
        dimensions = body.get("dimensions")
        dimension = dimensions[0]["name"] if dimensions else None
        return httpx.Response(200, json=load_sample(fixtures_by_dimension[dimension]))

    return handler


def make_client(handler, token_provider=lambda: "test-token") -> Ga4Client:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return Ga4Client(property_id="123456", token_provider=token_provider, client=http_client)


def test_daily_digest_maps_recorded_samples_to_domain_types():
    requests_seen: list[httpx.Request] = []
    client = make_client(fixture_handler(requests_seen))

    digest = client.fetch_daily_digest(SAMPLE_DAY)

    assert digest == make_sample_digest()
    assert len(requests_seen) == 4
    assert all(
        str(request.url).endswith("/properties/123456:runReport") for request in requests_seen
    )


def test_requests_carry_bearer_token_and_explicit_date_ranges():
    requests_seen: list[httpx.Request] = []
    client = make_client(fixture_handler(requests_seen))

    client.fetch_daily_digest(SAMPLE_DAY)

    totals_body = json.loads(requests_seen[0].content.decode("utf-8"))
    assert requests_seen[0].headers["Authorization"] == "Bearer test-token"
    assert totals_body["dateRanges"] == [
        {"startDate": "2026-07-07", "endDate": "2026-07-07"},
        {"startDate": "2026-07-06", "endDate": "2026-07-06"},
    ]


def test_request_vocabulary_matches_recorded_sample_headers():
    """Drift detection: the metric/dimension names sent must match the
    recorded response headers, so local literals can't silently diverge from
    the GA4 contract."""
    requests_seen: list[httpx.Request] = []
    client = make_client(fixture_handler(requests_seen))

    client.fetch_daily_digest(SAMPLE_DAY)

    for request, fixture_name in zip(requests_seen, FIXTURES_IN_REQUEST_ORDER):
        body = json.loads(request.content.decode("utf-8"))
        sample = load_sample(fixture_name)
        assert [metric["name"] for metric in body["metrics"]] == [
            header["name"] for header in sample["metricHeaders"]
        ], f"metric names drifted from {fixture_name}"
        if "dimensions" in body:
            assert [dimension["name"] for dimension in body["dimensions"]] == [
                header["name"] for header in sample["dimensionHeaders"]
            ], f"dimension names drifted from {fixture_name}"


def test_empty_report_maps_to_zero_totals_and_empty_tops():
    def handler(request: httpx.Request) -> httpx.Response:
        # GA4 omits `rows` entirely for a period with no data.
        return httpx.Response(200, json={"rowCount": 0, "kind": "analyticsData#runReport"})

    digest = make_client(handler).fetch_daily_digest(SAMPLE_DAY)

    assert digest.totals == DayTotals(0, 0, 0, 0)
    assert digest.prior_totals == DayTotals(0, 0, 0, 0)
    assert digest.top_pages == ()
    assert digest.top_channels == ()
    assert digest.top_events == ()


@pytest.mark.parametrize("status", [401, 403])
def test_auth_rejection_raises_auth_error(status):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"status": "PERMISSION_DENIED"}})

    with pytest.raises(AnalyticsAuthError):
        make_client(handler).fetch_daily_digest(SAMPLE_DAY)


def test_server_error_raises_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"status": "INTERNAL"}})

    with pytest.raises(AnalyticsTransportError):
        make_client(handler).fetch_daily_digest(SAMPLE_DAY)


def test_connection_failure_raises_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(AnalyticsTransportError):
        make_client(handler).fetch_daily_digest(SAMPLE_DAY)


def test_malformed_row_raises_response_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rows": [{"metricValues": [{"value": "not-a-number"}]}]})

    with pytest.raises(AnalyticsResponseError):
        make_client(handler).fetch_daily_digest(SAMPLE_DAY)


class TestServiceAccountAuth:
    def test_missing_key_file_raises_auth_error(self):
        with pytest.raises(AnalyticsAuthError):
            Ga4Client.from_service_account_file("/nonexistent/key.json", property_id="123456")

    def test_incomplete_service_account_info_raises_auth_error(self):
        provider = ServiceAccountTokenProvider(
            {}, httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
        )
        with pytest.raises(AnalyticsAuthError):
            provider()


class TestMetadataServerAuth:
    def test_returns_and_caches_token(self):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            assert request.headers["Metadata-Flavor"] == "Google"
            return httpx.Response(200, json={"access_token": "adc-token", "expires_in": 3600})

        clock_now = 1_000_000.0
        provider = MetadataServerTokenProvider(
            httpx.Client(transport=httpx.MockTransport(handler)), clock=lambda: clock_now
        )

        assert provider() == "adc-token"
        assert provider() == "adc-token"
        assert len(calls) == 1  # second call served from cache

    def test_unreachable_metadata_server_raises_auth_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no metadata server here", request=request)

        provider = MetadataServerTokenProvider(
            httpx.Client(transport=httpx.MockTransport(handler))
        )
        with pytest.raises(AnalyticsAuthError):
            provider()
