"""DailyDigest → Discord embed formatting.

The embed layout is a versioned contract (``ga_digest.v1``): the exact JSON
produced for a known input is pinned by the golden fixture
``tests/samples/discord_ga_digest_embed.json``. If you change anything here,
bump the footer version and regenerate the fixture deliberately — ports to
other languages/runtimes use that fixture as their correctness oracle.

Field order: Users, Sessions, Pageviews, New users (inline, with vs-prior-day
deltas), then Top pages, Top channels, Top events (block). Empty breakdowns
render "none"; a zero-traffic day renders zeros, not an error.
"""

from __future__ import annotations

from ga_discord_bridge.domain import DailyDigest, RankedRow

EMBED_COLOR = 0xE37400  # analytics orange

# Discord's hard limits; text is clamped, never rejected.
DISCORD_DESCRIPTION_LIMIT = 4096
DISCORD_FIELD_VALUE_LIMIT = 1024

EMBED_CONTRACT_VERSION = "ga_digest.v1"


def format_daily_digest_embed(digest: DailyDigest) -> dict[str, object]:
    """Map a :class:`~ga_discord_bridge.domain.DailyDigest` to one embed dict."""
    totals = digest.totals
    prior = digest.prior_totals
    fields = [
        {
            "name": "Users",
            "value": _format_count_with_delta(totals.active_users, prior.active_users),
            "inline": True,
        },
        {
            "name": "Sessions",
            "value": _format_count_with_delta(totals.sessions, prior.sessions),
            "inline": True,
        },
        {
            "name": "Pageviews",
            "value": _format_count_with_delta(totals.pageviews, prior.pageviews),
            "inline": True,
        },
        {
            "name": "New users",
            "value": _format_count_with_delta(totals.new_users, prior.new_users),
            "inline": True,
        },
        {
            "name": "Top pages",
            "value": _format_ranked_rows(digest.top_pages, code_labels=True),
            "inline": False,
        },
        {
            # GA4's sessionDefaultChannelGroup is a channel grouping
            # (Direct / Organic Search / Referral), not raw traffic sources.
            "name": "Top channels",
            "value": _format_ranked_rows(digest.top_channels),
            "inline": False,
        },
        {
            "name": "Top events",
            "value": _format_ranked_rows(digest.top_events),
            "inline": False,
        },
    ]
    description = (
        f"**{totals.active_users}** users · **{totals.sessions}** sessions · "
        f"**{totals.pageviews}** pageviews (deltas vs prior day)"
    )
    return {
        "title": f"Site analytics — {digest.day.isoformat()}",
        "description": _clamp_embed_text(description, DISCORD_DESCRIPTION_LIMIT),
        "color": EMBED_COLOR,
        "fields": fields,
        "footer": {"text": EMBED_CONTRACT_VERSION},
    }


def _format_count_with_delta(current: int, prior: int) -> str:
    delta = current - prior
    if delta > 0:
        rendered_delta = f"▲ {delta}"
    elif delta < 0:
        rendered_delta = f"▼ {abs(delta)}"
    else:
        rendered_delta = "— flat"
    return f"**{current}** ({rendered_delta})"


def _format_ranked_rows(rows: tuple[RankedRow, ...], *, code_labels: bool = False) -> str:
    if not rows:
        return "none"
    rendered = []
    for index, row in enumerate(rows, start=1):
        label = f"`{row.label}`" if code_labels else row.label
        rendered.append(f"{index}. {label} — {row.count}")
    return _clamp_embed_text("\n".join(rendered), DISCORD_FIELD_VALUE_LIMIT)


def _clamp_embed_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
