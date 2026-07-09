from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from ga_discord_bridge.domain import DailyDigest, DayTotals, RankedRow

SAMPLES_DIR = Path(__file__).parent / "samples"

# The day the recorded samples describe. Fixture numbers and the golden embed
# are all keyed to this date.
SAMPLE_DAY = date(2026, 7, 7)


def load_sample(name: str) -> dict[str, object]:
    return json.loads((SAMPLES_DIR / name).read_text(encoding="utf-8"))


def make_sample_digest(day: date = SAMPLE_DAY) -> DailyDigest:
    """The DailyDigest the recorded runReport samples parse into.

    Kept in one place so the parsing tests (raw JSON → domain) and the
    formatting tests (domain → embed) meet in the middle: together with the
    golden embed fixture they pin the whole pipeline end to end.
    """
    return DailyDigest(
        day=day,
        totals=DayTotals(active_users=12, sessions=15, pageviews=48, new_users=4),
        prior_totals=DayTotals(active_users=9, sessions=11, pageviews=53, new_users=4),
        top_pages=(
            RankedRow("/", 18),
            RankedRow("/scoreboard", 11),
            RankedRow("/autopsy/42", 6),
        ),
        top_channels=(
            RankedRow("Direct", 9),
            RankedRow("Organic Search", 4),
            RankedRow("Referral", 2),
        ),
        top_events=(
            RankedRow("page_view", 48),
            RankedRow("session_start", 15),
            RankedRow("proposal_viewed", 7),
        ),
    )


@pytest.fixture
def sample_digest() -> DailyDigest:
    return make_sample_digest()
