# ga-discord-bridge

Post a once-a-day **Google Analytics 4** digest to a **Discord** channel.

Every morning your channel gets one embed: users, sessions, and pageviews
with vs-prior-day deltas, plus the day's top pages, top channels, and top
events. That's the whole product.

```text
┌──────────────────────────────────────────┐
│ Site analytics — 2026-07-07              │
│ 12 users · 15 sessions · 48 pageviews    │
│                                          │
│ Users        Sessions      Pageviews     │
│ 12 (▲ 3)     15 (▲ 4)      48 (▼ 5)      │
│ New users                                │
│ 4 (— flat)                               │
│                                          │
│ Top pages                                │
│ 1. `/` — 18                              │
│ 2. `/scoreboard` — 11                    │
│                                          │
│ Top channels                             │
│ 1. Direct — 9                            │
│ 2. Organic Search — 4                    │
│                                          │
│ Top events                               │
│ 1. page_view — 48                        │
│ 2. session_start — 15                    │
│                        ga_digest.v1      │
└──────────────────────────────────────────┘
```

## Why this and not a GA client library + a bot?

- **Two dependencies.** `httpx` for every network call and `google-auth`
  purely for signing service-account JWTs. No GA client library, no grpc, no
  Discord bot framework — the Discord side is a plain incoming webhook.
- **Built for schedulers.** One shot per invocation, ~4 API calls, done in a
  couple of seconds. Runs identically as a Cloud Function for Firebase, a
  cron job, a GitHub Actions schedule, or `python -m ga_discord_bridge` on
  your laptop.
- **Keyless on GCP.** On Cloud Functions / Cloud Run / GCE it authenticates
  via the runtime service account (metadata server) — no key file to manage.
  Off GCP, point `GOOGLE_APPLICATION_CREDENTIALS` at a key file.
- **Failures are visible in the channel.** With `report_errors=True`
  (default in the deploy examples), a broken run posts a red "GA digest
  failed" embed with the error message to the same webhook — instead of
  dying silently in server logs — and still re-raises for the scheduler.
- **Fully offline test suite.** Recorded GA4 API responses and a golden
  embed fixture pin the whole pipeline; CI needs zero credentials.

## How it works

```text
        4 × runReport (yesterday, property TZ)      1 × POST {embeds:[…]}
GA4 ───────────────────────────────────────▶ digest ─────────────────────▶ Discord webhook
      totals (+prior day) · top pages ·
      top channels · top events
```

"Yesterday" is computed in the **GA property's reporting time zone**
(`GA_PROPERTY_TIMEZONE`) because that's the zone GA aggregates days in —
GA finishes processing a day overnight, so yesterday-there is the freshest
complete day. A day with no traffic posts zeros and "none", not an error.

## Install

Versioned by git tag — pin a release tag from the consumer's `pyproject.toml`:

```toml
dependencies = [
  "ga-discord-bridge @ git+https://github.com/Addryc/ga-discord-bridge@v0.2.0",
]
```

or with pip directly:

```bash
pip install "ga-discord-bridge @ git+https://github.com/Addryc/ga-discord-bridge@v0.2.0"
```

For local development of the package itself, use an editable install:

```bash
pip install -e /path/to/ga-discord-bridge
```

## Quickstart (local)

Prereqs: Python ≥ 3.11, a GA4 property, a Discord channel you can add a
webhook to. Full GA setup steps are in the next section.

```bash
pip install "ga-discord-bridge @ git+https://github.com/Addryc/ga-discord-bridge@v0.2.0"

export GA_PROPERTY_ID=123456789                        # numeric, from GA Admin
export GA_PROPERTY_TIMEZONE=UTC                        # match the property
export GOOGLE_APPLICATION_CREDENTIALS=./sa-key.json    # service-account key
export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/…

# See the embed without posting anywhere (also validates credentials):
python -m ga_discord_bridge --dry-run

# Post yesterday's digest for real:
python -m ga_discord_bridge

# Re-post a specific day:
python -m ga_discord_bridge --day 2026-07-01
```

## Setting up Google Analytics access

1. **Find the property id**: GA Admin → Property settings → *Property ID*.
   It's numeric. (The `G-XXXXXXX` string on your website is the
   *measurement id* — that's for sending data in, not reading it out, and it
   won't work here.)
2. **Create a service account** in any GCP project you control
   (IAM & Admin → Service accounts), and download a JSON key for it — or
   skip the key entirely if you'll run on GCP (see deployment options).
3. **Enable the Google Analytics Data API** on that GCP project:
   `gcloud services enable analyticsdata.googleapis.com` (or via the console).
4. **Grant the service account access to the property**: GA Admin →
   Property access management → add the service account's email
   (`something@project.iam.gserviceaccount.com`) with the **Viewer** role.
   Grants propagate in about a minute.

Missing step 3 or 4 produces a 403, which the bridge reports as:
`GA4 Data API rejected runReport with status 403 — check that the service
account has Viewer access to the property…`

## Setting up the Discord webhook

Channel settings → Integrations → Webhooks → **New Webhook** → Copy URL.
Treat the URL as a secret: anyone who has it can post to the channel.

## Deployment options

| Where | Auth | Guide |
|---|---|---|
| **Cloud Functions for Firebase** (scheduled) | runtime service account, no key file | [`examples/firebase/`](examples/firebase/) |
| **GitHub Actions** schedule (zero infra) | key file from repo secrets | [`examples/github-actions-cron.yml`](examples/github-actions-cron.yml) |
| **cron / systemd timer** | key file on disk | run `python -m ga_discord_bridge` daily, an hour or two after the property's midnight |

## Configuration reference

| Variable | Required | Meaning |
|---|---|---|
| `GA_PROPERTY_ID` | yes | Numeric GA4 property id |
| `DISCORD_WEBHOOK_URL` | for posting (not `--dry-run`) | Channel webhook to post to |
| `GA_PROPERTY_TIMEZONE` | recommended | IANA zone matching the property's reporting time zone; defaults to `UTC`. A mismatch makes "yesterday" straddle two GA days. |
| `GOOGLE_APPLICATION_CREDENTIALS` | off-GCP only | Path to a service-account key file. Leave unset on Cloud Functions / Cloud Run / GCE to use the runtime service account. |

See [.env.example](.env.example).

## What exactly gets reported

Four `runReport` calls against the GA4 Data API v1beta:

| Section | Dimension | Metric | Limit |
|---|---|---|---|
| Totals (+ prior day) | — (two date ranges) | `activeUsers`, `sessions`, `screenPageViews`, `newUsers` | — |
| Top pages | `pagePath` | `screenPageViews` | 5 |
| Top channels | `sessionDefaultChannelGroup` | `sessions` | 5 |
| Top events | `eventName` | `eventCount` | 8 |

Notes worth knowing:

- **"Top channels" are GA's channel groupings** (Direct / Organic Search /
  Referral…), not raw referrers. Want referrer-level detail? Swap the
  dimension to `sessionSource` in `ga4.py` — one line.
- **Custom events appear by name immediately** in Top events. Custom event
  *parameters*, however, are only queryable through the Data API after you
  register them as custom dimensions (GA Admin → Custom definitions), and
  only from registration onward (≈24 h lag). Register early.
- **The embed layout is a versioned contract** (`ga_digest.v1`, in the
  footer). Its exact JSON for a known input is pinned by
  [`tests/samples/discord_ga_digest_embed.json`](tests/samples/discord_ga_digest_embed.json) —
  if you port this pipeline to another language, that fixture is your
  correctness oracle.

## Using it as a library

```python
from ga_discord_bridge import run_from_env

run_from_env()  # env-configured, posts yesterday's digest
```

or with full control / your own scheduler:

```python
from datetime import date
from ga_discord_bridge import (
    DiscordWebhookClient, Ga4Client, resolve_digest_day, run_digest_once,
)

with Ga4Client.from_service_account_file("sa.json", property_id="123456789") as ga:
    with DiscordWebhookClient("https://discord.com/api/webhooks/…") as sink:
        run_digest_once(ga, sink, day=resolve_digest_day("Europe/London"))
```

`run_digest_once` takes any objects with `fetch_daily_digest(day)` /
`post_embed(embed)` methods, so you can swap either end (e.g. post to Slack
by writing a 20-line sink).

## Development

```bash
git clone https://github.com/Addryc/ga-discord-bridge
cd ga-discord-bridge
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest        # fully offline — recorded fixtures, no credentials
ruff check src tests
```

The test suite includes a **vocabulary drift check**: the GA4 metric and
dimension names the client sends are asserted against the names recorded in
real API responses (`tests/samples/ga4_run_report_*.json`), so a typo or an
upstream rename fails a test instead of silently zero-filling your digest.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `403 … check that the service account has Viewer access` | SA not added to the property (GA Admin → Property access management) or the Data API isn't enabled on the SA's project |
| `Cannot read service-account key file /abs/path…` | `GOOGLE_APPLICATION_CREDENTIALS` is relative to a different working directory — the message shows where it actually looked |
| `Could not fetch a token from the GCP metadata server` | You're running off-GCP without `GOOGLE_APPLICATION_CREDENTIALS` set |
| Digest is all zeros but the site had traffic | `GA_PROPERTY_TIMEZONE` doesn't match the property, or the property is new — GA needs to finish processing the day (run the morning after) |
| Numbers slightly lag GA's UI | Normal: the Data API and the UI can disagree by small amounts for ~24–48 h |

## License

[MIT](LICENSE)
