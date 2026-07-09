"""Environment-based configuration.

Only three values are ever required, and one of them only sometimes:

======================================  ============================================
``GA_PROPERTY_ID``                      numeric GA4 property id (GA Admin →
                                        Property settings; *not* the ``G-…``
                                        measurement id)
``DISCORD_WEBHOOK_URL``                 the channel webhook to post digests to
``GOOGLE_APPLICATION_CREDENTIALS``      path to a service-account key file;
                                        **omit on GCP** (Cloud Functions / Cloud
                                        Run / GCE) and the metadata server is
                                        used instead
======================================  ============================================

Optional:

======================================  ============================================
``GA_PROPERTY_TIMEZONE``                IANA zone matching the GA4 property's
                                        configured time zone (GA aggregates days in
                                        that zone). Defaults to ``UTC`` — set it,
                                        or your "yesterday" may straddle two GA
                                        days.
======================================  ============================================

No config framework on purpose: ``os.environ`` plus a frozen dataclass keeps
the dependency surface at zero and makes the Cloud Function story trivial
(env vars + Secret Manager).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ga_discord_bridge.errors import ConfigError

DEFAULT_PROPERTY_TIMEZONE = "UTC"


@dataclass(frozen=True, slots=True)
class Config:
    property_id: str
    # Optional at load time so --dry-run works without a webhook configured;
    # posting paths raise ConfigError when it is absent.
    webhook_url: str | None = None
    property_timezone: str = DEFAULT_PROPERTY_TIMEZONE
    service_account_json: str | None = None  # None → use the GCP metadata server

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Config":
        env = os.environ if environ is None else environ
        if not env.get("GA_PROPERTY_ID"):
            raise ConfigError("Missing required environment variable: GA_PROPERTY_ID")
        return cls(
            property_id=env["GA_PROPERTY_ID"],
            webhook_url=env.get("DISCORD_WEBHOOK_URL") or None,
            property_timezone=env.get("GA_PROPERTY_TIMEZONE") or DEFAULT_PROPERTY_TIMEZONE,
            service_account_json=env.get("GOOGLE_APPLICATION_CREDENTIALS") or None,
        )
