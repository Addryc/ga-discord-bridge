"""Orchestration + Discord client + config tests."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from ga_discord_bridge.config import Config
from ga_discord_bridge.digest import resolve_digest_day, run_digest_once, run_from_env
from ga_discord_bridge.discord import DiscordWebhookClient
from ga_discord_bridge.errors import ConfigError, DiscordWebhookResponseError
from ga_discord_bridge.format import format_daily_digest_embed
from tests.conftest import SAMPLE_DAY, make_sample_digest


class FakeAnalytics:
    def __init__(self):
        self.requested_days: list[date] = []

    def fetch_daily_digest(self, day: date):
        self.requested_days.append(day)
        return make_sample_digest(day)


def test_run_digest_once_posts_the_formatted_embed():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(204)

    analytics = FakeAnalytics()
    sink = DiscordWebhookClient(
        "https://discord.test/webhook", client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    digest = run_digest_once(analytics, sink, day=SAMPLE_DAY)

    assert analytics.requested_days == [SAMPLE_DAY]
    assert digest == make_sample_digest(SAMPLE_DAY)
    assert len(calls) == 1
    payload = json.loads(calls[0].content.decode("utf-8"))
    assert payload == {"embeds": [format_daily_digest_embed(digest)]}


def test_webhook_rejection_is_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Unknown Webhook"})

    sink = DiscordWebhookClient(
        "https://discord.test/webhook", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(DiscordWebhookResponseError):
        sink.post_embed({"title": "hello"})


def test_resolve_digest_day_uses_property_timezone():
    assert resolve_digest_day("UTC", today=date(2026, 7, 8)) == date(2026, 7, 7)


class TestConfig:
    def test_missing_property_id_raises_config_error(self):
        with pytest.raises(ConfigError):
            Config.from_env(environ={})

    def test_from_env_reads_all_values(self):
        config = Config.from_env(
            environ={
                "GA_PROPERTY_ID": "123456",
                "DISCORD_WEBHOOK_URL": "https://discord.test/webhook",
                "GA_PROPERTY_TIMEZONE": "Europe/London",
                "GOOGLE_APPLICATION_CREDENTIALS": "/keys/sa.json",
            }
        )
        assert config == Config(
            property_id="123456",
            webhook_url="https://discord.test/webhook",
            property_timezone="Europe/London",
            service_account_json="/keys/sa.json",
        )

    def test_defaults_are_utc_and_metadata_server(self):
        config = Config.from_env(environ={"GA_PROPERTY_ID": "123456"})
        assert config.property_timezone == "UTC"
        assert config.service_account_json is None
        assert config.webhook_url is None

    def test_posting_without_webhook_raises_config_error(self):
        with pytest.raises(ConfigError):
            run_from_env(config=Config(property_id="123456"), dry_run=False)
