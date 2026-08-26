# WxCC Analytics V2 Update

This update adds:

- automatic OAuth access-token refresh
- one retry after 401/403
- date-based historical backfill
- daily reconciliation of yesterday's data
- DST-safe day chunking
- Render/Postgres URL normalization

## Render environment variables

Set these on the web service AND both cron jobs:

```text
DATABASE_URL
WXCC_BASE_URL=https://api.wxcc-us1.cisco.com
WXCC_CLIENT_ID
WXCC_CLIENT_SECRET
WXCC_REFRESH_TOKEN
WXCC_TOKEN_URL=https://webexapis.com/v1/access_token
```

`WXCC_ACCESS_TOKEN` may be left blank once refresh credentials are working.

## Historical backfill

From Render Shell or locally:

```bash
python -m backend.app.jobs.backfill --start 2026-07-01 --end 2026-08-26
```

The utility:

- uses America/Detroit calendar days
- splits DST 25-hour days if necessary
- never submits a >24-hour Search window
- safely reuses existing IDs because normalized rows are upserted

## Nightly reconciliation

Render cron command:

```bash
python -m backend.app.jobs.reconcile_previous_day
```

This re-pulls yesterday so late wrap-up/callback/transfer changes overwrite the existing normalized records.

## Important refresh-token note

OAuth providers can rotate refresh tokens. The app will use a returned replacement refresh token for the life of that process, but a Render cron process cannot permanently rewrite its own environment variable.

For an initial deployment, verify whether your Webex token refresh response returns a new `refresh_token`.

If it rotates, the next production hardening step is to persist the current refresh token in PostgreSQL or a secret manager rather than only in Render environment variables.
