"""ga-discord-bridge — post a daily Google Analytics 4 digest to Discord.

Public surface:

- :func:`ga_discord_bridge.digest.run_from_env` — wire clients from env vars
  and run once (what the CLI and Cloud Function entrypoints call).
- :func:`ga_discord_bridge.digest.run_digest_once` — dependency-injected core
  for embedding in your own scheduler.
- :class:`ga_discord_bridge.ga4.Ga4Client`,
  :class:`ga_discord_bridge.discord.DiscordWebhookClient`,
  :func:`ga_discord_bridge.format.format_daily_digest_embed` — the pieces.
"""

from ga_discord_bridge.config import Config
from ga_discord_bridge.digest import resolve_digest_day, run_digest_once, run_from_env
from ga_discord_bridge.discord import DiscordWebhookClient
from ga_discord_bridge.domain import DailyDigest, DayTotals, RankedRow
from ga_discord_bridge.errors import (
    AnalyticsAuthError,
    AnalyticsError,
    AnalyticsResponseError,
    AnalyticsTransportError,
    BridgeError,
    ConfigError,
    DiscordWebhookError,
    DiscordWebhookResponseError,
    DiscordWebhookTransportError,
)
from ga_discord_bridge.format import format_daily_digest_embed, format_error_embed
from ga_discord_bridge.ga4 import Ga4Client

__version__ = "0.2.0"

__all__ = [
    "AnalyticsAuthError",
    "AnalyticsError",
    "AnalyticsResponseError",
    "AnalyticsTransportError",
    "BridgeError",
    "Config",
    "ConfigError",
    "DailyDigest",
    "DayTotals",
    "DiscordWebhookClient",
    "DiscordWebhookError",
    "DiscordWebhookResponseError",
    "DiscordWebhookTransportError",
    "Ga4Client",
    "RankedRow",
    "format_daily_digest_embed",
    "format_error_embed",
    "resolve_digest_day",
    "run_digest_once",
    "run_from_env",
    "__version__",
]
