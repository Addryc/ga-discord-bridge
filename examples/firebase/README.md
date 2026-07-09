# Deploying as a scheduled Cloud Function for Firebase

One scheduled 2nd-gen Cloud Function in your existing Firebase project. Cloud
Scheduler is provisioned automatically by the deploy. Requires the **Blaze**
plan (scheduled functions + outbound calls to Discord), but a daily
invocation costs effectively nothing, and the GA4 Data API quota is free.

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

4. **The webhook URL is a secret** — store it in Secret Manager:

   ```bash
   firebase functions:secrets:set DISCORD_WEBHOOK_URL
   ```

   The `secrets=["DISCORD_WEBHOOK_URL"]` binding in the decorator injects it
   at runtime.

5. **Grant GA access to the function's service account.** Find the runtime
   service account (default: `PROJECT_ID@appspot.gserviceaccount.com`; 2nd
   gen may use the compute default `PROJECT_NUMBER-compute@developer.gserviceaccount.com` —
   check the function's details page). Then in **GA Admin → Property access
   management**, add that email with the **Viewer** role. Also make sure the
   **Google Analytics Data API** is enabled on the GCP project:

   ```bash
   gcloud services enable analyticsdata.googleapis.com
   ```

6. **Deploy:**

   ```bash
   firebase deploy --only functions:daily_analytics_digest
   ```

## Verifying

Force a run without waiting for the schedule:

```bash
gcloud scheduler jobs list --location=us-central1   # find the job name
gcloud scheduler jobs run <job-name> --location=us-central1
```

Then check the channel for the embed and `firebase functions:log` for
errors. A `403 … check that the service account has Viewer access` error
means step 5 is incomplete (grants take ~a minute to propagate).
