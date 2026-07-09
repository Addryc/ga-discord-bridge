"""Error taxonomy.

Every third-party failure (httpx, google-auth, the GA4 Data API, the Discord
webhook API) is wrapped into one of these before it crosses a module
boundary, so callers can handle failures by *kind* without depending on the
underlying libraries:

- ``ConfigError`` — required configuration is missing or malformed; fix the
  environment, not the code.
- ``AnalyticsAuthError`` — credentials are unusable or the service account
  lacks access to the GA4 property (401/403, bad key file, signing failure).
- ``AnalyticsTransportError`` — the GA4 request failed in transit or the API
  rejected it with a non-auth HTTP status; usually transient, safe to retry.
- ``AnalyticsResponseError`` — GA4 answered 200 but the payload cannot be
  mapped into domain types; indicates an API contract change or a bug here.
- ``DiscordWebhookError`` family — same split for the Discord leg.
"""

from __future__ import annotations


class BridgeError(Exception):
    """Base class for every error this package raises deliberately."""


class ConfigError(BridgeError):
    """Required configuration is missing or malformed."""


class AnalyticsError(BridgeError):
    """Base error for the GA4 Data API boundary."""


class AnalyticsAuthError(AnalyticsError):
    """Authentication or authorization with Google failed."""


class AnalyticsTransportError(AnalyticsError):
    """The GA4 request failed in transit or returned a non-auth error status."""


class AnalyticsResponseError(AnalyticsError):
    """A GA4 payload could not be mapped into domain types."""


class DiscordWebhookError(BridgeError):
    """Base error for the Discord webhook boundary."""


class DiscordWebhookTransportError(DiscordWebhookError):
    """The webhook POST could not be sent."""


class DiscordWebhookResponseError(DiscordWebhookError):
    """Discord rejected the webhook POST."""
