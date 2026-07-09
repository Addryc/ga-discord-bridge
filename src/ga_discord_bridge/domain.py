"""Domain types for the daily analytics digest.

These are the *only* shapes that cross module boundaries: the GA4 client maps
raw API JSON into them, and the embed formatter maps them into a Discord
payload. Nothing outside :mod:`ga_discord_bridge.ga4` should ever see GA4's
response vocabulary, and nothing outside :mod:`ga_discord_bridge.format`
should ever build embed dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class DayTotals:
    """Whole-property counters for a single calendar day.

    GA4 metric mapping (see :mod:`ga_discord_bridge.ga4`):
    ``activeUsers``, ``sessions``, ``screenPageViews``, ``newUsers``.
    A day with no traffic is represented as all zeros, never as an error.
    """

    active_users: int
    sessions: int
    pageviews: int
    new_users: int


@dataclass(frozen=True, slots=True)
class RankedRow:
    """One label/count row of a top-N breakdown (page, channel, or event)."""

    label: str
    count: int


@dataclass(frozen=True, slots=True)
class DailyDigest:
    """Everything the daily digest reports for one day.

    ``prior_totals`` holds the previous calendar day's counters so the
    formatter can render vs-prior-day deltas. The top-N breakdowns are empty
    tuples (not ``None``) when the day has no data.
    """

    day: date
    totals: DayTotals
    prior_totals: DayTotals
    top_pages: tuple[RankedRow, ...]
    top_channels: tuple[RankedRow, ...]
    top_events: tuple[RankedRow, ...]
