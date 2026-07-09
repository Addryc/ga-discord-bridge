"""GA4 Data API client (REST ``runReport`` over httpx).

Design notes
------------

- **All GA4 vocabulary lives here.** Metric/dimension API names, the
  ``dimensionValues``/``metricValues`` response shape, and the implicit
  ``date_range_0``/``date_range_1`` keys are mapped to
  :mod:`ga_discord_bridge.domain` types in this module and nowhere else.
  ``tests/test_ga4.py`` pins the names against recorded API responses so a
  typo or upstream rename fails a test instead of silently zero-filling.
- **httpx is the only HTTP transport.** Even authentication avoids the
  google-auth transports: the service-account path signs an OAuth2
  JWT-bearer assertion (google-auth is used purely for RS256 signing) and
  exchanges it over httpx; the ADC path reads the GCE/Cloud Run/Cloud
  Functions metadata server directly. This keeps the dependency surface to
  ``httpx`` + ``google-auth`` and makes every network call mockable with
  ``httpx.MockTransport``.
- **Quiet days are data, not errors.** GA4 omits ``rows`` entirely for a day
  with no traffic; that maps to zero totals and empty breakdowns.
"""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import httpx

from ga_discord_bridge.domain import DailyDigest, DayTotals, RankedRow
from ga_discord_bridge.errors import (
    AnalyticsAuthError,
    AnalyticsResponseError,
    AnalyticsTransportError,
)

DATA_API_BASE_URL = "https://analyticsdata.googleapis.com/v1beta"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
ANALYTICS_READONLY_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"

# GCE / Cloud Run / Cloud Functions metadata server (Application Default
# Credentials without a key file). The Metadata-Flavor header is required.
METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)

_JWT_BEARER_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
_TOKEN_LIFETIME_SECONDS = 3600
_TOKEN_REFRESH_MARGIN_SECONDS = 60

# GA4 Data API metric/dimension names — the single place this vocabulary
# appears in code. Drift-detected against recorded samples in tests.
METRIC_ACTIVE_USERS = "activeUsers"
METRIC_SESSIONS = "sessions"
METRIC_PAGEVIEWS = "screenPageViews"
METRIC_NEW_USERS = "newUsers"
METRIC_EVENT_COUNT = "eventCount"
DIMENSION_PAGE_PATH = "pagePath"
DIMENSION_CHANNEL_GROUP = "sessionDefaultChannelGroup"
DIMENSION_EVENT_NAME = "eventName"

_TOTALS_METRICS = (METRIC_ACTIVE_USERS, METRIC_SESSIONS, METRIC_PAGEVIEWS, METRIC_NEW_USERS)

# With two date ranges and no explicit dimensions, GA4 adds an implicit
# dateRange dimension whose values are these keys.
_CURRENT_DATE_RANGE = "date_range_0"
_PRIOR_DATE_RANGE = "date_range_1"

TOP_PAGES_LIMIT = 5
TOP_CHANNELS_LIMIT = 5
TOP_EVENTS_LIMIT = 8


class Ga4Client:
    """Fetches one day's :class:`~ga_discord_bridge.domain.DailyDigest`.

    Construct directly with a ``token_provider`` (any zero-arg callable
    returning a bearer token — handy in tests), or use one of the
    classmethods:

    - :meth:`from_service_account_file` — local runs / anywhere with a
      downloaded key file.
    - :meth:`from_metadata_server` — Cloud Functions / Cloud Run / GCE,
      where the runtime service account provides tokens with no key file.
    """

    def __init__(
        self,
        *,
        property_id: str,
        token_provider: Callable[[], str],
        base_url: str = DATA_API_BASE_URL,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
        owns_client: bool | None = None,
    ) -> None:
        self._property_id = property_id
        self._token_provider = token_provider
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = (client is None) if owns_client is None else owns_client

    @classmethod
    def from_service_account_file(
        cls,
        key_path: str,
        *,
        property_id: str,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> "Ga4Client":
        try:
            info = json.loads(Path(key_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # Relative paths resolve against the process CWD; surface the
            # absolute resolution so a wrong-CWD invocation is diagnosable
            # from the message alone.
            raise AnalyticsAuthError(
                f"Cannot read service-account key file {Path(key_path).resolve()}"
            ) from exc
        http_client = client or httpx.Client(timeout=timeout)
        return cls(
            property_id=property_id,
            token_provider=ServiceAccountTokenProvider(info, http_client),
            timeout=timeout,
            client=http_client,
            owns_client=client is None,
        )

    @classmethod
    def from_metadata_server(
        cls,
        *,
        property_id: str,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> "Ga4Client":
        http_client = client or httpx.Client(timeout=timeout)
        return cls(
            property_id=property_id,
            token_provider=MetadataServerTokenProvider(http_client),
            timeout=timeout,
            client=http_client,
            owns_client=client is None,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "Ga4Client":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def fetch_daily_digest(self, day: date) -> DailyDigest:
        """Run the four reports that make up one day's digest.

        Request order is part of the test contract (totals, top pages, top
        channels, top events) — see ``tests/test_ga4.py``.
        """
        prior = day - timedelta(days=1)
        totals, prior_totals = self._fetch_totals(day, prior)
        return DailyDigest(
            day=day,
            totals=totals,
            prior_totals=prior_totals,
            top_pages=self._fetch_ranked(day, DIMENSION_PAGE_PATH, METRIC_PAGEVIEWS, TOP_PAGES_LIMIT),
            top_channels=self._fetch_ranked(
                day, DIMENSION_CHANNEL_GROUP, METRIC_SESSIONS, TOP_CHANNELS_LIMIT
            ),
            top_events=self._fetch_ranked(
                day, DIMENSION_EVENT_NAME, METRIC_EVENT_COUNT, TOP_EVENTS_LIMIT
            ),
        )

    def _fetch_totals(self, day: date, prior: date) -> tuple[DayTotals, DayTotals]:
        payload = self._run_report(
            {
                "dateRanges": [
                    {"startDate": day.isoformat(), "endDate": day.isoformat()},
                    {"startDate": prior.isoformat(), "endDate": prior.isoformat()},
                ],
                "metrics": [{"name": metric} for metric in _TOTALS_METRICS],
            }
        )
        by_range: dict[str, tuple[int, ...]] = {}
        for row in payload.get("rows") or []:
            range_key = _first_dimension_value(row)
            by_range[range_key] = _metric_ints(row, expected=len(_TOTALS_METRICS))
        return (
            _day_totals(by_range.get(_CURRENT_DATE_RANGE)),
            _day_totals(by_range.get(_PRIOR_DATE_RANGE)),
        )

    def _fetch_ranked(
        self, day: date, dimension: str, metric: str, limit: int
    ) -> tuple[RankedRow, ...]:
        payload = self._run_report(
            {
                "dateRanges": [{"startDate": day.isoformat(), "endDate": day.isoformat()}],
                "dimensions": [{"name": dimension}],
                "metrics": [{"name": metric}],
                "orderBys": [{"desc": True, "metric": {"metricName": metric}}],
                "limit": str(limit),
            }
        )
        rows = []
        for row in payload.get("rows") or []:
            label = _first_dimension_value(row)
            (count,) = _metric_ints(row, expected=1)
            rows.append(RankedRow(label=label, count=count))
        return tuple(rows)

    def _run_report(self, body: dict[str, object]) -> dict[str, object]:
        url = f"{self._base_url}/properties/{self._property_id}:runReport"
        headers = {"Authorization": f"Bearer {self._token_provider()}"}
        try:
            response = self._client.post(url, json=body, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in (401, 403):
                raise AnalyticsAuthError(
                    f"GA4 Data API rejected runReport with status {status_code} — check that"
                    " the service account has Viewer access to the property and that the"
                    " Google Analytics Data API is enabled on its project"
                ) from exc
            raise AnalyticsTransportError(
                f"GA4 Data API rejected runReport with status {status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AnalyticsTransportError("GA4 Data API request failed") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise AnalyticsResponseError("GA4 Data API returned a non-JSON body") from exc
        if not isinstance(payload, dict):
            raise AnalyticsResponseError("GA4 Data API returned an unexpected payload shape")
        return payload


class ServiceAccountTokenProvider:
    """OAuth2 JWT-bearer token exchange for a Google service account.

    Signs an assertion with the key file's private key (google-auth is used
    only for the RS256 signing) and exchanges it at Google's token endpoint
    over the shared httpx client. Tokens are cached until shortly before
    expiry.
    """

    def __init__(
        self,
        info: dict[str, object],
        client: httpx.Client,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._info = info
        self._client = client
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0

    def __call__(self) -> str:
        now = self._clock()
        if self._token is not None and now < self._expires_at - _TOKEN_REFRESH_MARGIN_SECONDS:
            return self._token

        assertion = self._signed_assertion(now)
        try:
            response = self._client.post(
                OAUTH_TOKEN_URL,
                data={"grant_type": _JWT_BEARER_GRANT_TYPE, "assertion": assertion},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise AnalyticsAuthError(
                f"Google OAuth token exchange failed with status {exc.response.status_code}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise AnalyticsAuthError("Google OAuth token exchange failed") from exc

        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise AnalyticsAuthError("Google OAuth token response did not include an access token")
        self._token = token
        self._expires_at = now + float(payload.get("expires_in") or _TOKEN_LIFETIME_SECONDS)
        return token

    def _signed_assertion(self, now: float) -> str:
        from google.auth import crypt as google_crypt
        from google.auth import jwt as google_jwt

        # Boundary rule: no google-auth (or underlying crypto) exception may
        # leak; anything raised while signing means the key is unusable.
        try:
            signer = google_crypt.RSASigner.from_service_account_info(self._info)
            issuer = self._info["client_email"]
            claims = {
                "iss": issuer,
                "scope": ANALYTICS_READONLY_SCOPE,
                "aud": OAUTH_TOKEN_URL,
                "iat": int(now),
                "exp": int(now) + _TOKEN_LIFETIME_SECONDS,
            }
            return google_jwt.encode(signer, claims).decode("ascii")
        except KeyError as exc:
            raise AnalyticsAuthError("Service-account key file is missing required fields") from exc
        except Exception as exc:
            raise AnalyticsAuthError("Service-account key could not sign the OAuth assertion") from exc


class MetadataServerTokenProvider:
    """Application Default Credentials via the GCP metadata server.

    Inside Cloud Functions / Cloud Run / GCE, the runtime's service account
    hands out tokens at a fixed link-local URL — no key file anywhere. Grant
    that service account Viewer on the GA4 property and this Just Works.
    Fails with :class:`AnalyticsAuthError` when not running on GCP.
    """

    def __init__(
        self,
        client: httpx.Client,
        clock: Callable[[], float] = time.time,
        token_url: str = METADATA_TOKEN_URL,
    ) -> None:
        self._client = client
        self._clock = clock
        self._token_url = token_url
        self._token: str | None = None
        self._expires_at = 0.0

    def __call__(self) -> str:
        now = self._clock()
        if self._token is not None and now < self._expires_at - _TOKEN_REFRESH_MARGIN_SECONDS:
            return self._token

        try:
            response = self._client.get(self._token_url, headers={"Metadata-Flavor": "Google"})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AnalyticsAuthError(
                "Could not fetch a token from the GCP metadata server — this auth mode only"
                " works on Cloud Functions / Cloud Run / GCE; set"
                " GOOGLE_APPLICATION_CREDENTIALS to a key file for local runs"
            ) from exc

        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise AnalyticsAuthError("Metadata server response did not include an access token")
        self._token = token
        self._expires_at = now + float(payload.get("expires_in") or _TOKEN_LIFETIME_SECONDS)
        return token


def _first_dimension_value(row: dict[str, object]) -> str:
    values = row.get("dimensionValues")
    if not isinstance(values, list) or not values or not isinstance(values[0], dict):
        raise AnalyticsResponseError("GA4 report row is missing dimension values")
    value = values[0].get("value")
    if not isinstance(value, str):
        raise AnalyticsResponseError("GA4 report row has a non-string dimension value")
    return value


def _metric_ints(row: dict[str, object], *, expected: int) -> tuple[int, ...]:
    values = row.get("metricValues")
    if not isinstance(values, list) or len(values) != expected:
        raise AnalyticsResponseError("GA4 report row is missing expected metric values")
    counts = []
    for entry in values:
        raw = entry.get("value") if isinstance(entry, dict) else None
        try:
            counts.append(int(float(raw)))  # GA serializes numbers as strings
        except (TypeError, ValueError) as exc:
            raise AnalyticsResponseError(f"GA4 metric value {raw!r} is not numeric") from exc
    return tuple(counts)


def _day_totals(counts: tuple[int, ...] | None) -> DayTotals:
    if counts is None:
        counts = (0, 0, 0, 0)
    active_users, sessions, pageviews, new_users = counts
    return DayTotals(
        active_users=active_users,
        sessions=sessions,
        pageviews=pageviews,
        new_users=new_users,
    )
