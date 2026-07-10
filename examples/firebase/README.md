# Deploying as a scheduled Cloud Function for Firebase

One scheduled 2nd-gen Cloud Function in your existing Firebase project. Cloud
Scheduler is provisioned automatically by the deploy. Requires the **Blaze**
plan (scheduled functions + outbound calls to Discord), but a daily
invocation costs effectively nothing, and the GA4 Data API quota is free.

## Who can deploy (permissions)

Project **Owner** covers everything. If you're deploying into someone else's
project with scoped roles, you need all four — learned from real deploys:

| Role | Why |
|---|---|
| **Editor** | build + deploy, enable APIs, Cloud Scheduler |
| **Cloud Functions Admin** | the deploy's final step grants Cloud Scheduler permission to *invoke* the function — an IAM change Editor can't make (the deploy fails with `Failed to set the IAM Policy on the Service…` and rolls back cleanly) |
| **Secret Manager Admin** | creating the webhook secret *and* granting the runtime service account access to it |
| **Service Account User** | the function runs as the project's compute service account |

If your project has other functions or extensions, put this one in its own
[functions codebase](https://firebase.google.com/docs/functions/organize-functions)
(`"codebase": "ga-digest"` in `firebase.json`) — deploys are then strictly
scoped and cannot touch anything outside it.

## One-time setup

1. **Initialize Python functions** in your Firebase project (skip if you
   already have a `functions/` directory on the Python runtime):

   ```bash
   firebase init functions   # choose Python
   ```

2. **Copy the example in:** put [`main.py`](main.py) and the two dependency
   lines from [`requirements.txt`](requirements.txt) into your `functions/`
   directory. Adjust `schedule` and `timezone` in the decorator — the
   timezone should match your GA4 property's reporting time zone.

3. **Non-secret config** goes in `functions/.env` (deployed with the code,
   fine for non-secrets):

   ```bash
   GA_PROPERTY_ID=123456789
   GA_PROPERTY_TIMEZONE=UTC
   ```

   Do **not** set `GOOGLE_APPLICATION_CREDENTIALS` — on Cloud Functions the
   bridge uses the runtime service account automatically.

4. **The webhook URL is a secret** — store it in Secret Manager
   (interactive prompt, or pipe it with `--data-file=-`):

   ```bash
   firebase functions:secrets:set DISCORD_WEBHOOK_URL
   # or, non-interactively:
   printf '%s' "$WEBHOOK_URL" | firebase functions:secrets:set DISCORD_WEBHOOK_URL --data-file=-
   ```

   The `secrets=["DISCORD_WEBHOOK_URL"]` binding in the decorator injects it
   at runtime; the deploy grants the runtime service account access to the
   secret automatically.

5. **Grant GA access to the function's service account.** 2nd-gen functions
   run as the **compute default** service account:
   `PROJECT_NUMBER-compute@developer.gserviceaccount.com` (the project
   *number*, not id — it's printed in the deploy output, or run
   `gcloud projects describe PROJECT_ID --format='value(projectNumber)'`).
   In **GA Admin → Property access management**, add that email with the
   **Viewer** role (grants propagate in about a minute). Also make sure the
   **Google Analytics Data API** is enabled on the GCP project:

   ```bash
   gcloud services enable analyticsdata.googleapis.com
   ```

6. **Deploy:**

   ```bash
   firebase deploy --only functions:daily_analytics_digest
   ```

   The first deploy enables several APIs (Cloud Run, Eventarc, Cloud
   Scheduler, Pub/Sub) automatically and may warn about a missing container
   image **cleanup policy** — set one so old images don't accumulate a small
   storage bill:

   ```bash
   firebase functions:artifacts:setpolicy --location us-central1 --days 3 --force
   ```

## Verifying

Force a run without waiting for the schedule (the job is named
`firebase-schedule-<function>-<region>`):

```bash
gcloud scheduler jobs run firebase-schedule-daily_analytics_digest-us-central1 --location=us-central1
```

Then check the channel for the embed. Because the example passes
`report_errors=True`, a *failed* run also shows up in the channel as a red
"GA digest failed" embed carrying the error message — the channel itself is
your monitor. In logs, a healthy run is an HTTP 200
in a couple of seconds plus an INFO line `Posted GA digest for YYYY-MM-DD`
(that line needs the `logging.basicConfig` from `main.py` — without it,
successful runs look empty in Cloud Logging). A
`403 … check that the service account has Viewer access` error means step 5
is incomplete (grants take ~a minute to propagate).
