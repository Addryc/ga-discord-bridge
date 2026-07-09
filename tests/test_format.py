"""Embed formatting tests.

``discord_ga_digest_embed.json`` is the golden fixture for the ga_digest.v1
contract — ports of this pipeline to other languages should reproduce it
byte-for-byte from the same input (see ``conftest.make_sample_digest``).
"""

from __future__ import annotations

from dataclasses import replace

from ga_discord_bridge.format import (
    DISCORD_FIELD_VALUE_LIMIT,
    format_daily_digest_embed,
)
from ga_discord_bridge.domain import RankedRow
from tests.conftest import load_sample


def test_sample_digest_maps_to_golden_embed(sample_digest):
    embed = format_daily_digest_embed(sample_digest)

    assert embed == load_sample("discord_ga_digest_embed.json")
    # The field order is the ga_digest.v1 contract.
    assert [field["name"] for field in embed["fields"]] == [
        "Users",
        "Sessions",
        "Pageviews",
        "New users",
        "Top pages",
        "Top channels",
        "Top events",
    ]
    assert "timestamp" not in embed


def test_empty_breakdowns_render_none(sample_digest):
    digest = replace(sample_digest, top_pages=(), top_channels=(), top_events=())

    embed = format_daily_digest_embed(digest)

    breakdowns = [field["value"] for field in embed["fields"] if field["name"].startswith("Top")]
    assert breakdowns == ["none", "none", "none"]


def test_deltas_cover_up_down_and_flat(sample_digest):
    values = {field["name"]: field["value"] for field in format_daily_digest_embed(sample_digest)["fields"]}

    assert values["Users"] == "**12** (▲ 3)"
    assert values["Pageviews"] == "**48** (▼ 5)"
    assert values["New users"] == "**4** (— flat)"


def test_long_breakdowns_are_clamped_to_discord_limits(sample_digest):
    digest = replace(
        sample_digest,
        top_pages=tuple(RankedRow(f"/very/long/path/segment/{i}/" + "x" * 60, i) for i in range(40)),
    )

    embed = format_daily_digest_embed(digest)

    top_pages = next(field["value"] for field in embed["fields"] if field["name"] == "Top pages")
    assert len(top_pages) <= DISCORD_FIELD_VALUE_LIMIT
    assert top_pages.endswith("…")
