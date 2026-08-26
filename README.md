# WxCC Analytics

Render-hosted Webex Contact Center analytics foundation.

## What is already implemented

- PostgreSQL schema for:
  - interactions
  - interaction_agents
  - interaction_legs
  - raw_wxcc_records
  - collector_runs
- Validated WxCC Search API pulls for:
  - `task`
  - `taskDetails`
  - `taskLegDetails`
- Raw JSONB retention for every fetched record.
- Upsert behavior so overlapping 15-minute collection windows are safe.
- Collector-run auditing / data-health endpoint.
- 24-hour maximum search-window protection.
- Initial dashboard metrics:
  - total interactions
  - inbound
  - outdial
  - answered
  - abandoned
  - answer rate
  - abandon rate
  - average/max queue wait
  - successful native callbacks
  - per-agent connected/ringing/wrapup/hold totals
- Render Blueprint for:
  - web service
  - PostgreSQL
  - 15-minute cron collector

## Important metric rules

Do not classify a call as answered just because an agent exists.

Use:

- Answered = `connectedCount > 0`
- Abandoned = `terminationType == "abandoned"`
- Queue wait = `queue.duration`
- Ring time = `ringingDuration`
- Talk time = `connectedDuration`
- Hold time = `holdDuration`
- ACW = `wrapupDuration`
- Agent = `owner` / `lastAgent`
- Agent outbound = `direction == "outdial"`
- Native callback success = `callbackData.callbackStatus == "Success"`

An abandoned interaction can still show an agent because the call may have been offered/ringing but never connected.

## Local setup

Create a virtual environment, install dependencies, copy `.env.example` to `.env`, then configure:

```bash
pip install -r requirements.txt
cp .env.example .env
```

Start:

```bash
uvicorn backend.app.main:app --reload
```

Open:

- `/`
- `/docs`
- `/api/health`
- `/api/data-health`
- `/api/dashboard/overview`
- `/api/dashboard/agents`

## Manual collector test

Use an epoch-millisecond window of 24 hours or less:

```bash
curl -X POST \
  "http://localhost:8000/api/collector/run?from_ms=1787616000000&to_ms=1787702400000"
```

## Render deployment

1. Push this project to GitHub.
2. In Render, create a Blueprint from `render.yaml`.
3. Enter the WxCC secrets as protected environment variables.
4. Deploy.
5. Run one manual collector request against a known historical one-day window.
6. Confirm `/api/data-health`.
7. Confirm records in `/api/dashboard/overview`.
8. Let the 15-minute cron begin ongoing collection.

## Token strategy

The current starter accepts `WXCC_ACCESS_TOKEN`.

For production, the next enhancement should be automatic OAuth refresh using:

- `WXCC_CLIENT_ID`
- `WXCC_CLIENT_SECRET`
- `WXCC_REFRESH_TOKEN`

Do not store credentials in source control.

## Backfill strategy

The Search API window must be chunked to no more than 24 hours.

For historical backfill:

```text
day 1 -> collect
day 2 -> collect
day 3 -> collect
...
```

Use overlapping or repeated windows safely because normalized records are upserted by task/leg IDs.

## Data we still need before the dashboard is complete

Phase 2/3:

- Agent session/state history
  - logged-in time
  - available time
  - not-ready / aux
  - occupancy
  - coverage gaps
- SLA target configuration
- service-level interval metrics
- entry-point / team dimensions
- business-hours / holiday calendar
- queue presented/handled interval summaries
- callback correlation for manual outbound callbacks
- voicemail reason/instrumentation
- unresolved missed calls >24h
- WoW / MoM / seasonality aggregates
- staffing-vs-demand interval table
- daily/hourly materialized summaries
- data-retention policy
- app authentication / customer access control
- alerting for collector failures
- token-refresh automation
- nightly reconciliation job
- historical backfill command
- production dashboard UI

## Recommended next build order

1. Deploy this foundation.
2. Validate one day of data in PostgreSQL.
3. Add automatic OAuth refresh.
4. Add backfill utility.
5. Add agent-state/session collector.
6. Add SLA and queue interval metrics.
7. Add voicemail/callback follow-up logic.
8. Build full dashboard pages.
9. Add anomaly/insight layer.
