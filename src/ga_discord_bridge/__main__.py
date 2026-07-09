"""CLI entrypoint: ``python -m ga_discord_bridge``.

Reads configuration from the environment (see README / config.py) and posts
one digest. Examples::

    # Post yesterday's digest (property time zone) to the webhook
    python -m ga_discord_bridge

    # Check credentials and inspect the embed without posting
    python -m ga_discord_bridge --dry-run

    # Re-post a specific day
    python -m ga_discord_bridge --day 2026-07-01
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from ga_discord_bridge.digest import run_from_env
from ga_discord_bridge.errors import BridgeError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ga-discord-bridge",
        description="Post a daily Google Analytics 4 digest to a Discord channel.",
    )
    parser.add_argument(
        "--day",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="report this specific day instead of yesterday (property time zone)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch from GA and print the embed JSON instead of posting to Discord",
    )
    parser.add_argument("--verbose", action="store_true", help="log HTTP requests")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    try:
        run_from_env(day=args.day, dry_run=args.dry_run)
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
