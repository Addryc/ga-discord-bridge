"""Scheduled Cloud Function for Firebase (Python) posting the daily digest.

Deploy from a standard Firebase `functions/` directory containing this file
and the requirements.txt next to it — see examples/firebase/README.md for
the full walkthrough.

Auth note: no key file anywhere. The function's runtime service account
(PROJECT_ID@appspot.gserviceaccount.com by default) provides tokens via the
metadata server; grant *that* account Viewer on the GA4 property.
"""

import logging

from firebase_functions import scheduler_fn

from ga_discord_bridge import run_from_env

# The bridge logs its outcome ("Posted GA digest for …") at INFO; without
# this, Python's default WARNING threshold swallows it and successful runs
# look empty in Cloud Logging.
logging.basicConfig(level=logging.INFO)


@scheduler_fn.on_schedule(
    # Runs daily at 08:00 in the given zone. Match `timezone` to the GA4
    # property's reporting time zone (and set GA_PROPERTY_TIMEZONE to the
    # same value) so "yesterday" is a complete GA day.
    schedule="every day 08:00",
    timezone=scheduler_fn.Timezone("UTC"),
    # The webhook URL lives in Secret Manager, not in code or env files:
    #   firebase functions:secrets:set DISCORD_WEBHOOK_URL
    secrets=["DISCORD_WEBHOOK_URL"],
)
def daily_analytics_digest(event: scheduler_fn.ScheduledEvent) -> None:
    # GA_PROPERTY_ID / GA_PROPERTY_TIMEZONE come from functions/.env (see
    # README); DISCORD_WEBHOOK_URL is injected by the secrets binding above.
    run_from_env(report_errors=True)
