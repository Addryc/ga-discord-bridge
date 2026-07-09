"""Orchestration: fetch one day's digest and post it to Discord.

The pipeline in one sentence: pick "yesterday" in the GA property's time
zone, run four GA4 reports, format one embed, POST it to a webhook.

``run_digest_once`` is dependency-injected (any analytics fetcher / any
embed poster) so tests and alternative frontends can reuse it;
``run_from_env`` wires the real clients from environment configuration and
is what the CLI and the Cloud Function entrypoints call.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from ga_discord_bridge.config import Config
from ga_discord_bridge.domain import DailyDigest
from ga_discord_bridge.format import format_daily_digest_embed

logger = logging.getLogger(__name__)


class AnalyticsSource(Protocol):
    def fetch_daily_digest(self, day: date) -> DailyDigest: ...


class EmbedSink(Protocol):
    def post_embed(self, embed: dict[str, object]) -> None: ...


def resolve_digest_day(property_timezone: str, today: date | None = None) -> date:
    """Yesterday, in the GA property's configured time zone.

    GA4 finishes aggregating a calendar day (in the *property's* zone)
    overnight, so "yesterday there" is the freshest complete day. Using the
    machine's local zone instead is the classic off-by-one-day bug this
    function exists to prevent.
    """
    current = today or datetime.now(ZoneInfo(property_timezone)).date()
    return current - timedelta(days=1)


def run_digest_once(
    analytics: AnalyticsSource,
    sink: EmbedSink,
    *,
    day: date,
) -> DailyDigest:
    """Fetch ``day``'s digest, format it, and post it. Returns the digest."""
    digest = analytics.fetch_daily_digest(day)
    sink.post_embed(format_daily_digest_embed(digest))
    logger.info("Posted GA digest for %s", day.isoformat())
    return digest


def run_from_env(
    *,
    day: date | None = None,
    dry_run: bool = False,
    config: Config | None = None,
    emit: Callable[[str], None] = print,
) -> DailyDigest:
    """Wire real clients from the environment and run once.

    ``dry_run`` fetches from GA but prints the embed JSON via ``emit``
    instead of posting to Discord — useful for checking credentials and
    output shape without touching the channel.
    """
    import json

    from ga_discord_bridge.discord import DiscordWebhookClient
    from ga_discord_bridge.errors import ConfigError
    from ga_discord_bridge.ga4 import Ga4Client

    active_config = config or Config.from_env()
    if not dry_run and not active_config.webhook_url:
        raise ConfigError("DISCORD_WEBHOOK_URL is required (or run with --dry-run)")
    digest_day = day or resolve_digest_day(active_config.property_timezone)

    if active_config.service_account_json is not None:
        analytics = Ga4Client.from_service_account_file(
            active_config.service_account_json,
            property_id=active_config.property_id,
        )
    else:
        analytics = Ga4Client.from_metadata_server(property_id=active_config.property_id)

    with analytics:
        if dry_run:
            digest = analytics.fetch_daily_digest(digest_day)
            emit(json.dumps(format_daily_digest_embed(digest), indent=2, ensure_ascii=False))
            return digest
        with DiscordWebhookClient(active_config.webhook_url) as sink:
            return run_digest_once(analytics, sink, day=digest_day)
