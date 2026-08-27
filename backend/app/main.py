from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from .database import Base, engine
from .routes.health import router as health_router
from .routes.collector import router as collector_router
from .routes.dashboard import router as dashboard_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="WxCC Analytics",
    version="4.1",
    description="Render-hosted Webex Contact Center analytics collector and dashboard.",
)

app.include_router(health_router)
app.include_router(collector_router)
app.include_router(dashboard_router)


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>WxCC Analytics</title>
      <style>
        :root {
          --bg:#f4f7f6;
          --panel:#ffffff;
          --ink:#15221d;
          --muted:#68756f;
          --line:#dfe7e3;
          --brand:#1f7a4c;
          --brand-dark:#145c38;
          --soft:#eaf5ef;
        }
        * { box-sizing:border-box; }
        body {
          margin:0;
          font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background:var(--bg);
          color:var(--ink);
        }
        .shell { max-width:1180px; margin:0 auto; padding:42px 24px; }
        .hero {
          background:linear-gradient(135deg,#153f2c,#1f7a4c);
          color:white;
          border-radius:24px;
          padding:42px;
          box-shadow:0 18px 45px rgba(23,72,48,.18);
        }
        .eyebrow {
          font-size:12px; font-weight:800; letter-spacing:.14em;
          text-transform:uppercase; opacity:.78;
        }
        h1 { margin:8px 0 10px; font-size:42px; line-height:1.05; }
        .hero p { max-width:720px; margin:0; color:#dceee4; font-size:17px; }
        .actions { display:flex; gap:12px; flex-wrap:wrap; margin-top:28px; }
        .btn {
          text-decoration:none;
          border-radius:12px;
          padding:12px 17px;
          font-weight:750;
          display:inline-flex;
          align-items:center;
          gap:8px;
        }
        .btn-primary { background:white; color:var(--brand-dark); }
        .btn-secondary { background:rgba(255,255,255,.12); color:white; border:1px solid rgba(255,255,255,.2); }
        .grid {
          display:grid;
          grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
          gap:16px;
          margin-top:22px;
        }
        .card {
          background:var(--panel);
          border:1px solid var(--line);
          border-radius:18px;
          padding:21px;
        }
        .card strong { display:block; font-size:18px; margin-bottom:6px; }
        .card span { color:var(--muted); font-size:14px; line-height:1.5; }
        .status { margin-top:20px; font-size:13px; color:var(--muted); }
      </style>
    </head>
    <body>
      <main class="shell">
        <section class="hero">
          <div class="eyebrow">Webex Contact Center</div>
          <h1>Analytics Dashboard</h1>
          <p>Operational reporting for contact demand, staffing, service performance, and customer experience.</p>
          <div class="actions">
            <a class="btn btn-primary" href="/staffing">Open Agent & Staffing →</a>
            <a class="btn btn-secondary" href="/call-demand">Open Call Demand</a>
            <a class="btn btn-secondary" href="/docs">API Docs</a>
          </div>
        </section>
        <section class="grid">
          <div class="card"><strong>Agent & Staffing</strong><span>Login coverage, availability, idle time, utilization, occupancy and RONA.</span></div>
          <div class="card"><strong>Call Demand</strong><span>Inbound and outbound volume, time-of-day patterns, missed calls and queue demand.</span></div>
          <div class="card"><strong>Service & SLA</strong><span>Answer rate, abandon rate, wait time and service-level performance.</span></div>
          <div class="card"><strong>Missed & Callback</strong><span>Voicemail, callbacks, unresolved contacts and follow-up performance.</span></div>
        </section>
        <div class="status">Dashboard backend v4.1</div>
      </main>
    </body>
    </html>
    """


@app.get("/staffing", response_class=HTMLResponse)
def staffing_page():
    return r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Agent & Staffing | WxCC Analytics</title>
  <style>
    :root {
      --bg:#f3f6f5;
      --panel:#ffffff;
      --ink:#17221d;
      --muted:#69766f;
      --line:#dde6e1;
      --brand:#1f7a4c;
      --brand-dark:#145c38;
      --brand-soft:#e9f5ee;
      --warn:#9a6700;
      --warn-bg:#fff7dd;
      --bad:#b42318;
      --bad-bg:#fff0ee;
      --shadow:0 7px 24px rgba(20,55,39,.07);
    }

    * { box-sizing:border-box; }
    html { background:var(--bg); }
    body {
      margin:0;
      font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:var(--bg);
      color:var(--ink);
    }

    button, input, select { font:inherit; }

    .topbar {
      height:66px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      padding:0 28px;
      background:#173d2b;
      color:white;
      position:sticky;
      top:0;
      z-index:10;
      box-shadow:0 2px 12px rgba(0,0,0,.12);
    }

    .brand { display:flex; align-items:center; gap:12px; }
    .mark {
      width:34px; height:34px;
      display:grid; place-items:center;
      border-radius:10px;
      background:#2b8f5d;
      font-weight:900;
    }
    .brand-title { font-weight:800; }
    .brand-sub { font-size:12px; color:#bbd7c7; margin-top:1px; }
    .top-link { color:#d8eadf; text-decoration:none; font-size:13px; }

    .page {
      max-width:1500px;
      margin:0 auto;
      padding:28px;
    }

    .heading-row {
      display:flex;
      justify-content:space-between;
      align-items:flex-end;
      gap:18px;
      margin-bottom:20px;
      flex-wrap:wrap;
    }

    h1 { margin:0; font-size:30px; letter-spacing:-.025em; }
    .subtitle { margin-top:5px; color:var(--muted); font-size:14px; }

    .filters {
      background:var(--panel);
      border:1px solid var(--line);
      border-radius:16px;
      padding:16px;
      display:grid;
      grid-template-columns:minmax(140px,1fr) minmax(140px,1fr) minmax(180px,1fr) minmax(180px,1.25fr) auto;
      gap:12px;
      align-items:end;
      box-shadow:var(--shadow);
      margin-bottom:18px;
    }

    .field label {
      display:block;
      font-size:11px;
      text-transform:uppercase;
      letter-spacing:.07em;
      font-weight:800;
      color:var(--muted);
      margin-bottom:6px;
    }

    .field input, .field select {
      width:100%;
      height:40px;
      border:1px solid #cfdad4;
      border-radius:10px;
      background:white;
      padding:0 11px;
      color:var(--ink);
      outline:none;
    }

    .field input:focus, .field select:focus {
      border-color:#64a981;
      box-shadow:0 0 0 3px rgba(31,122,76,.10);
    }

    .apply {
      height:40px;
      border:0;
      border-radius:10px;
      padding:0 18px;
      font-weight:800;
      color:white;
      background:var(--brand);
      cursor:pointer;
    }
    .apply:hover { background:var(--brand-dark); }

    .kpis {
      display:grid;
      grid-template-columns:repeat(7,minmax(125px,1fr));
      gap:12px;
      margin-bottom:18px;
    }

    .kpi {
      background:var(--panel);
      border:1px solid var(--line);
      border-radius:15px;
      padding:17px;
      box-shadow:var(--shadow);
      min-width:0;
    }
    .kpi-label {
      font-size:11px;
      color:var(--muted);
      text-transform:uppercase;
      letter-spacing:.06em;
      font-weight:800;
      white-space:nowrap;
      overflow:hidden;
      text-overflow:ellipsis;
    }
    .kpi-value {
      margin-top:7px;
      font-size:25px;
      line-height:1;
      font-weight:850;
      letter-spacing:-.03em;
    }
    .kpi-foot {
      margin-top:7px;
      color:var(--muted);
      font-size:11px;
    }

    .panel {
      background:var(--panel);
      border:1px solid var(--line);
      border-radius:17px;
      box-shadow:var(--shadow);
      overflow:hidden;
    }

    .panel-head {
      min-height:60px;
      padding:14px 18px;
      border-bottom:1px solid var(--line);
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:14px;
      flex-wrap:wrap;
    }

    .panel-title { font-size:16px; font-weight:850; }
    .panel-meta { color:var(--muted); font-size:12px; margin-top:2px; }

    .legend {
      display:flex;
      align-items:center;
      gap:14px;
      flex-wrap:wrap;
      color:var(--muted);
      font-size:11px;
    }

    .dot {
      display:inline-block;
      width:8px; height:8px;
      border-radius:50%;
      background:var(--brand);
      margin-right:5px;
    }
    .dot.warn { background:#d49a24; }

    .table-wrap { overflow:auto; max-height:calc(100vh - 360px); }

    table {
      width:100%;
      min-width:1250px;
      border-collapse:separate;
      border-spacing:0;
      font-size:13px;
    }

    th {
      position:sticky;
      top:0;
      background:#f7f9f8;
      z-index:2;
      text-align:right;
      padding:12px 12px;
      color:#536159;
      font-size:10px;
      text-transform:uppercase;
      letter-spacing:.055em;
      border-bottom:1px solid var(--line);
      cursor:pointer;
      user-select:none;
      white-space:nowrap;
    }

    th:first-child, th:nth-child(2) { text-align:left; }

    td {
      text-align:right;
      padding:12px;
      border-bottom:1px solid #edf1ef;
      white-space:nowrap;
      font-variant-numeric:tabular-nums;
    }

    td:first-child, td:nth-child(2) { text-align:left; }
    tbody tr:hover { background:#f8fbf9; }
    tbody tr:last-child td { border-bottom:0; }

    .agent { font-weight:780; }
    .team { color:var(--muted); }

    .pill {
      display:inline-flex;
      align-items:center;
      border-radius:999px;
      padding:4px 8px;
      font-size:10px;
      font-weight:800;
    }
    .pill.good { background:var(--brand-soft); color:var(--brand-dark); }
    .pill.warn { background:var(--warn-bg); color:var(--warn); }

    .metric-bar {
      display:inline-flex;
      align-items:center;
      gap:7px;
      min-width:86px;
      justify-content:flex-end;
    }
    .bar {
      width:38px; height:5px; border-radius:99px;
      background:#e7eeea; overflow:hidden;
    }
    .bar > span {
      display:block; height:100%;
      background:var(--brand);
      border-radius:99px;
    }

    .empty, .error {
      padding:42px 24px;
      text-align:center;
      color:var(--muted);
    }
    .error { color:var(--bad); background:var(--bad-bg); }

    .loading {
      opacity:.58;
      pointer-events:none;
    }

    .info-btn {
      height:38px;
      border:1px solid #bfd4c7;
      border-radius:10px;
      padding:0 13px;
      background:#ffffff;
      color:var(--brand-dark);
      font-weight:800;
      cursor:pointer;
      box-shadow:0 2px 8px rgba(20,55,39,.04);
    }

    .info-btn:hover {
      background:var(--brand-soft);
    }

    .modal-backdrop {
      position:fixed;
      inset:0;
      background:rgba(15,28,22,.48);
      display:none;
      align-items:center;
      justify-content:center;
      padding:24px;
      z-index:50;
    }

    .modal-backdrop.open {
      display:flex;
    }

    .modal-card {
      width:min(760px,100%);
      max-height:86vh;
      overflow:auto;
      background:white;
      border-radius:20px;
      border:1px solid var(--line);
      box-shadow:0 24px 70px rgba(0,0,0,.24);
    }

    .modal-head {
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:16px;
      padding:20px 22px 16px;
      border-bottom:1px solid var(--line);
      position:sticky;
      top:0;
      background:white;
      z-index:2;
    }

    .modal-title {
      font-size:19px;
      font-weight:850;
    }

    .modal-close {
      width:34px;
      height:34px;
      border:0;
      border-radius:9px;
      background:#f1f5f3;
      color:var(--ink);
      font-size:20px;
      cursor:pointer;
    }

    .metric-defs {
      padding:8px 22px 22px;
    }

    .metric-def {
      padding:15px 0;
      border-bottom:1px solid #edf1ef;
    }

    .metric-def:last-child {
      border-bottom:0;
    }

    .metric-def strong {
      display:block;
      font-size:14px;
      margin-bottom:4px;
    }

    .metric-def p {
      margin:0;
      color:var(--muted);
      font-size:13px;
      line-height:1.55;
    }

    .metric-formula {
      display:inline-block;
      margin-top:6px;
      padding:5px 8px;
      border-radius:8px;
      background:#f4f7f6;
      color:#405047;
      font-size:12px;
      font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    @media (max-width:1200px) {
      .kpis { grid-template-columns:repeat(4,1fr); }
      .filters { grid-template-columns:repeat(2,1fr); }
      .filters .apply { width:100%; }
    }

    @media (max-width:700px) {
      .page { padding:18px 12px; }
      .topbar { padding:0 14px; }
      .kpis { grid-template-columns:repeat(2,1fr); }
      .filters { grid-template-columns:1fr; }
      h1 { font-size:25px; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <div class="mark">W</div>
      <div>
        <div class="brand-title">WxCC Analytics</div>
        <div class="brand-sub">Agent & Staffing</div>
      </div>
    </div>
    <a class="top-link" href="/">Dashboard Home</a>
  </header>

  <main class="page" id="page">
    <div class="heading-row">
      <div>
        <h1>Agent & Staffing</h1>
        <div class="subtitle">Login coverage, agent states, utilization, occupancy and RONA performance.</div>
      </div>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <button class="info-btn" id="metricInfoBtn" type="button">ⓘ Metric Definitions</button>
        <div class="subtitle" id="version">Loading backend…</div>
      </div>
    </div>

    <section class="filters">
      <div class="field">
        <label for="fromDate">From</label>
        <input id="fromDate" type="date">
      </div>
      <div class="field">
        <label for="toDate">Through</label>
        <input id="toDate" type="date">
      </div>
      <div class="field">
        <label for="teamFilter">Team</label>
        <select id="teamFilter">
          <option value="">All teams</option>
        </select>
      </div>
      <div class="field">
        <label for="agentSearch">Agent Search</label>
        <input id="agentSearch" type="search" placeholder="Search agent name…">
      </div>
      <button class="apply" id="applyBtn">Apply</button>
    </section>

    <section class="kpis">
      <div class="kpi">
        <div class="kpi-label">Agents</div>
        <div class="kpi-value" id="kpiAgents">—</div>
        <div class="kpi-foot">in current view</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Logged In</div>
        <div class="kpi-value" id="kpiLogged">—</div>
        <div class="kpi-foot">total agent hours</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Available</div>
        <div class="kpi-value" id="kpiAvailable">—</div>
        <div class="kpi-foot">total available hours</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Idle / Not Ready</div>
        <div class="kpi-value" id="kpiIdle">—</div>
        <div class="kpi-foot">total idle hours</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Utilization</div>
        <div class="kpi-value" id="kpiUtil">—</div>
        <div class="kpi-foot">weighted by login time</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Occupancy</div>
        <div class="kpi-value" id="kpiOcc">—</div>
        <div class="kpi-foot">available + active work</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">RONA Events</div>
        <div class="kpi-value" id="kpiRona">—</div>
        <div class="kpi-foot" id="kpiComplete">—</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">Agent Detail</div>
          <div class="panel-meta" id="resultMeta">Loading staffing data…</div>
        </div>
        <div class="legend">
          <span><i class="dot"></i>Complete data</span>
          <span><i class="dot warn"></i>Needs review</span>
          <span>Click column headers to sort</span>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th data-sort="agent_name">Agent</th>
              <th data-sort="team_name">Team</th>
              <th data-sort="logged_in_hours">Logged In</th>
              <th data-sort="available_hours">Available</th>
              <th data-sort="idle_hours">Idle</th>
              <th data-sort="connected_hours">Talk</th>
              <th data-sort="wrapup_hours">ACW</th>
              <th data-sort="rona_events">RONA</th>
              <th data-sort="availability_percent">Availability</th>
              <th data-sort="utilization_percent">Utilization</th>
              <th data-sort="occupancy_percent">Occupancy</th>
              <th data-sort="accounted_percent">Data Quality</th>
            </tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
        <div id="message"></div>
      </div>
    </section>
  </main>

  <div class="modal-backdrop" id="metricModal" aria-hidden="true">
    <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="metricModalTitle">
      <div class="modal-head">
        <div>
          <div class="modal-title" id="metricModalTitle">Metric Definitions</div>
          <div class="subtitle">How to interpret Agent & Staffing metrics.</div>
        </div>
        <button class="modal-close" id="metricModalClose" type="button" aria-label="Close">×</button>
      </div>

      <div class="metric-defs">
        <div class="metric-def">
          <strong>Logged In</strong>
          <p>Total time the agent was logged into Webex Contact Center during the selected reporting window.</p>
        </div>

        <div class="metric-def">
          <strong>Available</strong>
          <p>Time the agent was ready and available to receive queue work.</p>
        </div>

        <div class="metric-def">
          <strong>Idle / Not Ready</strong>
          <p>Time the agent was logged in but not available to receive queue work.</p>
        </div>

        <div class="metric-def">
          <strong>Talk</strong>
          <p>Time actively connected to customer interactions.</p>
        </div>

        <div class="metric-def">
          <strong>ACW</strong>
          <p>After Call Work / wrap-up time spent completing work after an interaction.</p>
        </div>

        <div class="metric-def">
          <strong>RONA Events</strong>
          <p>Number of explicit not-responding events recorded by Webex Contact Center when an interaction was offered and the agent did not respond.</p>
        </div>

        <div class="metric-def">
          <strong>Availability %</strong>
          <p>Shows how much of the agent's logged-in time was spent available for queue work.</p>
          <span class="metric-formula">Available ÷ Logged In</span>
        </div>

        <div class="metric-def">
          <strong>Utilization %</strong>
          <p>Shows how much of the agent's entire logged-in time was spent actively handling customer work or completing after-call work.</p>
          <span class="metric-formula">(Talk + ACW) ÷ Logged In</span>
        </div>

        <div class="metric-def">
          <strong>Occupancy %</strong>
          <p>Shows how busy the agent was during time they were actually eligible for queue work. Idle / Not Ready time is excluded from the denominator.</p>
          <span class="metric-formula">(Talk + ACW) ÷ (Available + Talk + ACW)</span>
        </div>

        <div class="metric-def">
          <strong>Data Quality</strong>
          <p>Indicates whether enough agent-state activity was captured to trust the staffing calculations. Complete means at least 99% of logged-in time is accounted for.</p>
        </div>
      </div>
    </div>
  </div>

<script>
  let rawRows = [];
  let sortKey = 'logged_in_hours';
  let sortDir = -1;

  const $ = id => document.getElementById(id);
  const fmtHours = n => {
    const value = Number(n || 0);
    if (value > 0 && value < 0.01) return '<0.01h';
    return `${value.toFixed(2)}h`;
  };
  const fmtPct = n => `${Number(n || 0).toFixed(2)}%`;
  const escapeHtml = value => String(value ?? '')
    .replaceAll('&','&amp;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;')
    .replaceAll('"','&quot;')
    .replaceAll("'","&#039;");

  function localDayStartMs(dateText) {
    if (!dateText) return null;
    const [y,m,d] = dateText.split('-').map(Number);
    return new Date(y, m - 1, d, 0, 0, 0, 0).getTime();
  }

  function localDayAfterMs(dateText) {
    if (!dateText) return null;
    const [y,m,d] = dateText.split('-').map(Number);
    return new Date(y, m - 1, d + 1, 0, 0, 0, 0).getTime();
  }

  function buildUrl() {
    const params = new URLSearchParams();
    const from = localDayStartMs($('fromDate').value);
    const to = localDayAfterMs($('toDate').value);

    if (from !== null) params.set('from_ms', from);
    if (to !== null) params.set('to_ms', to);

    const qs = params.toString();
    return '/api/dashboard/staffing' + (qs ? '?' + qs : '');
  }

  function updateTeamOptions(rows) {
    const previous = $('teamFilter').value;
    const teams = [...new Set(rows.map(r => r.team_name).filter(Boolean))].sort();
    $('teamFilter').innerHTML =
      '<option value="">All teams</option>' +
      teams.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');

    if (teams.includes(previous)) $('teamFilter').value = previous;
  }

  function filteredRows() {
    const team = $('teamFilter').value;
    const search = $('agentSearch').value.trim().toLowerCase();

    return rawRows.filter(row => {
      const teamOk = !team || row.team_name === team;
      const searchOk = !search || String(row.agent_name || '').toLowerCase().includes(search);
      return teamOk && searchOk;
    });
  }

  function weightedPercent(rows, numeratorFields, denominatorFields) {
    let numerator = 0;
    let denominator = 0;

    for (const row of rows) {
      for (const f of numeratorFields) numerator += Number(row[f] || 0);
      for (const f of denominatorFields) denominator += Number(row[f] || 0);
    }

    return denominator ? numerator / denominator * 100 : 0;
  }

  function renderKpis(rows) {
    const sum = field => rows.reduce((a,r) => a + Number(r[field] || 0), 0);
    const productiveFields = ['connected_ms','wrapup_ms'];

    $('kpiAgents').textContent = rows.length;
    $('kpiLogged').textContent = (sum('logged_in_ms') / 3600000).toFixed(1) + 'h';
    $('kpiAvailable').textContent = (sum('available_ms') / 3600000).toFixed(1) + 'h';
    $('kpiIdle').textContent = (sum('idle_ms') / 3600000).toFixed(1) + 'h';

    const utilization = weightedPercent(rows, productiveFields, ['logged_in_ms']);
    const occupancy = weightedPercent(
      rows,
      productiveFields,
      ['available_ms','connected_ms','wrapup_ms']
    );

    $('kpiUtil').textContent = utilization.toFixed(1) + '%';
    $('kpiOcc').textContent = occupancy.toFixed(1) + '%';
    $('kpiRona').textContent = sum('rona_events');

    const complete = rows.filter(r => r.staffing_data_complete).length;
    $('kpiComplete').textContent = `${complete}/${rows.length} complete`;
  }

  function metricCell(percent) {
    const p = Math.max(0, Math.min(Number(percent || 0), 100));
    return `
      <span class="metric-bar">
        <span>${p.toFixed(2)}%</span>
        <span class="bar"><span style="width:${p}%"></span></span>
      </span>`;
  }

  function renderTable(rows) {
    const body = $('tbody');
    const message = $('message');

    if (!rows.length) {
      body.innerHTML = '';
      message.innerHTML = '<div class="empty">No staffing records match the current filters.</div>';
      $('resultMeta').textContent = '0 agents';
      return;
    }

    message.innerHTML = '';

    const sorted = [...rows].sort((a,b) => {
      const av = a[sortKey];
      const bv = b[sortKey];

      if (typeof av === 'string' || typeof bv === 'string') {
        return String(av ?? '').localeCompare(String(bv ?? '')) * sortDir;
      }
      return (Number(av || 0) - Number(bv || 0)) * sortDir;
    });

    body.innerHTML = sorted.map(row => `
      <tr>
        <td class="agent">${escapeHtml(row.agent_name || 'Unknown')}</td>
        <td class="team">${escapeHtml(row.team_name || '—')}</td>
        <td>${fmtHours(row.logged_in_hours)}</td>
        <td>${fmtHours(row.available_hours)}</td>
        <td>${fmtHours(row.idle_hours)}</td>
        <td>${fmtHours(row.connected_hours)}</td>
        <td>${fmtHours(row.wrapup_hours)}</td>
        <td>${Number(row.rona_events || 0)}</td>
        <td>${metricCell(row.availability_percent)}</td>
        <td>${metricCell(row.utilization_percent)}</td>
        <td>${metricCell(row.occupancy_percent)}</td>
        <td>
          <span class="pill ${row.staffing_data_complete ? 'good' : 'warn'}">
            ${row.staffing_data_complete ? 'Complete' : `${Number(row.accounted_percent || 0).toFixed(1)}%`}
          </span>
        </td>
      </tr>
    `).join('');

    const teams = new Set(rows.map(r => r.team_name).filter(Boolean));
    $('resultMeta').textContent = `${rows.length} agents across ${teams.size} teams`;
  }

  function rerender() {
    const rows = filteredRows();
    renderKpis(rows);
    renderTable(rows);
  }

  async function loadStaffing() {
    const page = $('page');
    page.classList.add('loading');
    $('message').innerHTML = '';
    $('resultMeta').textContent = 'Loading staffing data…';

    try {
      const response = await fetch(buildUrl());
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
      }

      rawRows = await response.json();
      updateTeamOptions(rawRows);
      rerender();

      const version = rawRows[0]?.backend_version || 'unknown';
      $('version').textContent = `Backend v${version}`;
    } catch (err) {
      rawRows = [];
      $('tbody').innerHTML = '';
      $('message').innerHTML =
        `<div class="error">Could not load staffing data.<br>${escapeHtml(err.message)}</div>`;
      $('resultMeta').textContent = 'Load failed';
    } finally {
      page.classList.remove('loading');
    }
  }

  document.querySelectorAll('th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (sortKey === key) {
        sortDir *= -1;
      } else {
        sortKey = key;
        sortDir = (key === 'agent_name' || key === 'team_name') ? 1 : -1;
      }
      rerender();
    });
  });

  $('applyBtn').addEventListener('click', loadStaffing);
  $('teamFilter').addEventListener('change', rerender);
  $('agentSearch').addEventListener('input', rerender);

  const metricModal = $('metricModal');
  $('metricInfoBtn').addEventListener('click', () => {
    metricModal.classList.add('open');
    metricModal.setAttribute('aria-hidden', 'false');
  });

  $('metricModalClose').addEventListener('click', () => {
    metricModal.classList.remove('open');
    metricModal.setAttribute('aria-hidden', 'true');
  });

  metricModal.addEventListener('click', event => {
    if (event.target === metricModal) {
      metricModal.classList.remove('open');
      metricModal.setAttribute('aria-hidden', 'true');
    }
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && metricModal.classList.contains('open')) {
      metricModal.classList.remove('open');
      metricModal.setAttribute('aria-hidden', 'true');
    }
  });

  // Leave dates blank by default so the first load shows all collected data.
  loadStaffing();
</script>
</body>
</html>
    """


@app.get("/call-demand", response_class=HTMLResponse)
def call_demand_page():
    return r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Call Demand | WxCC Analytics</title>
  <style>
    :root {
      --bg:#f3f6f5; --panel:#fff; --ink:#17221d; --muted:#69766f;
      --line:#dde6e1; --brand:#1f7a4c; --brand-dark:#145c38;
      --brand-soft:#e9f5ee; --danger:#b42318; --danger-soft:#fff0ee;
      --amber:#9a6700; --shadow:0 7px 24px rgba(20,55,39,.07);
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--ink)}
    button,input,select{font:inherit}
    .topbar{height:66px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;background:#173d2b;color:#fff;position:sticky;top:0;z-index:10;box-shadow:0 2px 12px rgba(0,0,0,.12)}
    .brand{display:flex;align-items:center;gap:12px}.mark{width:34px;height:34px;display:grid;place-items:center;border-radius:10px;background:#2b8f5d;font-weight:900}
    .brand-title{font-weight:800}.brand-sub{font-size:12px;color:#bbd7c7;margin-top:1px}
    .nav{display:flex;gap:16px}.nav a{color:#d8eadf;text-decoration:none;font-size:13px}.nav a.active{color:#fff;font-weight:800}
    .page{max-width:1500px;margin:0 auto;padding:28px}
    .heading-row{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;margin-bottom:20px;flex-wrap:wrap}
    h1{margin:0;font-size:30px;letter-spacing:-.025em}.subtitle{margin-top:5px;color:var(--muted);font-size:14px}
    .filters{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px;display:grid;grid-template-columns:minmax(150px,1fr) minmax(150px,1fr) auto;gap:12px;align-items:end;box-shadow:var(--shadow);margin-bottom:18px}
    .field label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.07em;font-weight:800;color:var(--muted);margin-bottom:6px}
    .field input{width:100%;height:40px;border:1px solid #cfdad4;border-radius:10px;background:#fff;padding:0 11px;color:var(--ink)}
    .apply,.info-btn{height:40px;border-radius:10px;padding:0 17px;font-weight:800;cursor:pointer}
    .apply{border:0;background:var(--brand);color:#fff}.apply:hover{background:var(--brand-dark)}
    .info-btn{border:1px solid #bfd4c7;background:#fff;color:var(--brand-dark)}
    .kpis{display:grid;grid-template-columns:repeat(8,minmax(120px,1fr));gap:12px;margin-bottom:18px}
    .kpi{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:17px;box-shadow:var(--shadow);min-width:0}
    .kpi-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .kpi-value{margin-top:7px;font-size:24px;line-height:1;font-weight:850;letter-spacing:-.03em}.kpi-foot{margin-top:7px;color:var(--muted);font-size:10px}
    .grid2{display:grid;grid-template-columns:1.25fr .75fr;gap:18px;margin-bottom:18px}
    .panel{background:var(--panel);border:1px solid var(--line);border-radius:17px;box-shadow:var(--shadow);overflow:hidden}
    .panel-head{min-height:58px;padding:14px 18px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:12px}
    .panel-title{font-size:16px;font-weight:850}.panel-meta{color:var(--muted);font-size:11px;margin-top:2px}
    .bars{padding:18px;height:330px;display:flex;align-items:flex-end;gap:7px;overflow-x:auto}
    .bar-col{min-width:30px;flex:1;text-align:center}
    .bar-stack{height:230px;display:flex;align-items:flex-end;justify-content:center;gap:2px}
    .bar-in{width:10px;background:var(--brand);border-radius:5px 5px 0 0;min-height:1px}
    .bar-ab{width:7px;background:#d56b60;border-radius:5px 5px 0 0;min-height:0}
    .bar-label{font-size:9px;color:var(--muted);margin-top:7px;white-space:nowrap}
    .bar-value{font-size:9px;font-weight:800;margin-bottom:3px}
    .trend{padding:18px}
    .trend-row{display:grid;grid-template-columns:100px 1fr 70px;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid #edf1ef}
    .trend-row:last-child{border-bottom:0}.trend-track{height:9px;background:#e9efec;border-radius:99px;overflow:hidden}.trend-fill{height:100%;background:var(--brand);border-radius:99px}
    .queue-wrap{overflow:auto;max-height:520px}
    table{width:100%;min-width:900px;border-collapse:separate;border-spacing:0;font-size:13px}
    th{position:sticky;top:0;background:#f7f9f8;text-align:right;padding:12px;color:#536159;font-size:10px;text-transform:uppercase;letter-spacing:.055em;border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap}
    th:first-child,td:first-child{text-align:left}
    td{text-align:right;padding:12px;border-bottom:1px solid #edf1ef;white-space:nowrap;font-variant-numeric:tabular-nums}
    tbody tr:hover{background:#f8fbf9}.queue-name{font-weight:780}
    .pill{display:inline-flex;border-radius:999px;padding:4px 8px;font-size:10px;font-weight:800}.good{background:var(--brand-soft);color:var(--brand-dark)}.warn{background:#fff7dd;color:var(--amber)}.bad{background:var(--danger-soft);color:var(--danger)}
    .note{padding:13px 18px;background:#f7faf8;color:#5f6e66;font-size:11px;border-top:1px solid var(--line)}
    .modal-backdrop{position:fixed;inset:0;background:rgba(15,28,22,.48);display:none;align-items:center;justify-content:center;padding:24px;z-index:50}.modal-backdrop.open{display:flex}
    .modal-card{width:min(720px,100%);max-height:86vh;overflow:auto;background:#fff;border-radius:20px;box-shadow:0 24px 70px rgba(0,0,0,.24)}
    .modal-head{display:flex;justify-content:space-between;align-items:center;padding:20px 22px 16px;border-bottom:1px solid var(--line);position:sticky;top:0;background:#fff}
    .modal-title{font-size:19px;font-weight:850}.modal-close{width:34px;height:34px;border:0;border-radius:9px;background:#f1f5f3;font-size:20px;cursor:pointer}
    .defs{padding:8px 22px 22px}.def{padding:14px 0;border-bottom:1px solid #edf1ef}.def:last-child{border:0}.def strong{display:block;font-size:14px;margin-bottom:4px}.def p{margin:0;color:var(--muted);font-size:13px;line-height:1.5}
    .formula{display:inline-block;margin-top:6px;padding:5px 8px;border-radius:8px;background:#f4f7f6;font-size:12px;font-family:ui-monospace,monospace}
    .loading{opacity:.6;pointer-events:none}.message{padding:36px;text-align:center;color:var(--muted)}
    @media(max-width:1200px){.kpis{grid-template-columns:repeat(4,1fr)}.grid2{grid-template-columns:1fr}}
    @media(max-width:700px){.page{padding:18px 12px}.topbar{padding:0 14px}.kpis{grid-template-columns:repeat(2,1fr)}.filters{grid-template-columns:1fr}h1{font-size:25px}}
  </style>
</head>
<body>
<header class="topbar">
  <div class="brand"><div class="mark">W</div><div><div class="brand-title">WxCC Analytics</div><div class="brand-sub">Call Demand</div></div></div>
  <nav class="nav"><a href="/">Home</a><a href="/staffing">Staffing</a><a class="active" href="/call-demand">Call Demand</a></nav>
</header>

<main class="page" id="page">
  <div class="heading-row">
    <div><h1>Call Demand</h1><div class="subtitle">Inbound demand, queue performance, timing patterns and outbound activity.</div></div>
    <div style="display:flex;align-items:center;gap:10px"><button class="info-btn" id="infoBtn">ⓘ Metric Definitions</button><div class="subtitle" id="version">Loading backend…</div></div>
  </div>

  <section class="filters">
    <div class="field"><label>From</label><input id="fromDate" type="date"></div>
    <div class="field"><label>Through</label><input id="toDate" type="date"></div>
    <button class="apply" id="applyBtn">Apply</button>
  </section>

  <section class="kpis">
    <div class="kpi"><div class="kpi-label">Total Inbound</div><div class="kpi-value" id="inbound">—</div><div class="kpi-foot">all inbound interactions</div></div>
    <div class="kpi"><div class="kpi-label">Queued Inbound</div><div class="kpi-value" id="queued">—</div><div class="kpi-foot" id="unqueued">—</div></div>
    <div class="kpi"><div class="kpi-label">Answered</div><div class="kpi-value" id="answered">—</div><div class="kpi-foot">queued interactions</div></div>
    <div class="kpi"><div class="kpi-label">Abandoned</div><div class="kpi-value" id="abandoned">—</div><div class="kpi-foot">queued interactions</div></div>
    <div class="kpi"><div class="kpi-label">Queue Answer Rate</div><div class="kpi-value" id="answerRate">—</div><div class="kpi-foot">answered ÷ queued inbound</div></div>
    <div class="kpi"><div class="kpi-label">Queue Abandon Rate</div><div class="kpi-value" id="abandonRate">—</div><div class="kpi-foot">abandoned ÷ queued inbound</div></div>
    <div class="kpi"><div class="kpi-label">Avg Queue Wait</div><div class="kpi-value" id="avgWait">—</div><div class="kpi-foot">queued inbound</div></div>
    <div class="kpi"><div class="kpi-label">Peak Hour</div><div class="kpi-value" id="peakHour">—</div><div class="kpi-foot" id="peakHourFoot">—</div></div>
  </section>

  <section class="grid2">
    <div class="panel">
      <div class="panel-head"><div><div class="panel-title">Inbound Demand by Hour</div><div class="panel-meta">Green = inbound · red = abandoned</div></div></div>
      <div class="bars" id="hourlyBars"></div>
    </div>
    <div class="panel">
      <div class="panel-head"><div><div class="panel-title">Daily Volume</div><div class="panel-meta">Inbound interactions by local calendar day</div></div></div>
      <div class="trend" id="dailyTrend"></div>
    </div>
  </section>

  <section class="panel">
    <div class="panel-head"><div><div class="panel-title">Queue Performance</div><div class="panel-meta" id="queueMeta">Loading…</div></div></div>
    <div class="queue-wrap">
      <table>
        <thead><tr>
          <th data-sort="queue_name">Queue</th>
          <th data-sort="offered">Offered</th>
          <th data-sort="answered">Answered</th>
          <th data-sort="abandoned">Abandoned</th>
          <th data-sort="answer_rate">Answer %</th>
          <th data-sort="abandon_rate">Abandon %</th>
          <th data-sort="avg_queue_seconds">Avg Wait</th>
          <th data-sort="max_queue_seconds">Max Wait</th>
        </tr></thead>
        <tbody id="queueBody"></tbody>
      </table>
    </div>
    <div class="note">“Unassigned / No Queue” is intentionally excluded from queued-inbound KPI rates because those interactions never entered a stored queue.</div>
  </section>
</main>

<div class="modal-backdrop" id="modal" aria-hidden="true">
  <div class="modal-card">
    <div class="modal-head"><div><div class="modal-title">Call Demand Metric Definitions</div><div class="subtitle">How the dashboard classifies interactions.</div></div><button class="modal-close" id="closeBtn">×</button></div>
    <div class="defs">
      <div class="def"><strong>Total Inbound</strong><p>Every interaction whose direction is inbound, whether or not it ultimately entered a queue.</p></div>
      <div class="def"><strong>Queued Inbound</strong><p>Inbound interactions with a stored queue name. These form the denominator for operational queue answer and abandon rates.</p></div>
      <div class="def"><strong>Answered</strong><p>Queued inbound interactions where Webex recorded at least one connected segment.</p><span class="formula">connected_count &gt; 0</span></div>
      <div class="def"><strong>Abandoned</strong><p>Queued inbound interactions whose termination type is abandoned.</p><span class="formula">termination_type == abandoned</span></div>
      <div class="def"><strong>Queue Answer Rate</strong><p>Percentage of queued inbound interactions that were answered.</p><span class="formula">Queued Answered ÷ Queued Inbound</span></div>
      <div class="def"><strong>Queue Abandon Rate</strong><p>Percentage of queued inbound interactions abandoned by the caller.</p><span class="formula">Queued Abandoned ÷ Queued Inbound</span></div>
      <div class="def"><strong>Queue Wait</strong><p>Time recorded in the task-level queue duration field. The dashboard shows average and maximum wait for queued inbound interactions.</p></div>
      <div class="def"><strong>Queue Performance</strong><p>Interactions are grouped by the task-level final/last queue so transferred interactions are not counted multiple times across queue legs.</p></div>
    </div>
  </div>
</div>

<script>
const $=id=>document.getElementById(id);
let data=null, sortKey='offered', sortDir=-1;

function localStart(s){if(!s)return null;const[y,m,d]=s.split('-').map(Number);return new Date(y,m-1,d,0,0,0,0).getTime()}
function localAfter(s){if(!s)return null;const[y,m,d]=s.split('-').map(Number);return new Date(y,m-1,d+1,0,0,0,0).getTime()}
function url(){const p=new URLSearchParams();const f=localStart($('fromDate').value),t=localAfter($('toDate').value);if(f!==null)p.set('from_ms',f);if(t!==null)p.set('to_ms',t);p.set('timezone',Intl.DateTimeFormat().resolvedOptions().timeZone||'America/Detroit');return '/api/dashboard/call-demand?'+p.toString()}
function pct(n){return `${Number(n||0).toFixed(2)}%`}
function wait(s){s=Number(s||0);if(s<60)return `${s.toFixed(1)}s`;const m=Math.floor(s/60),r=Math.round(s%60);return `${m}m ${r}s`}
function esc(v){return String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')}

function renderOverview(o){
  $('inbound').textContent=o.inbound;
  $('queued').textContent=o.queued_inbound;
  $('unqueued').textContent=`${o.no_queue_inbound} did not enter a queue`;
  $('answered').textContent=o.queued_answered;
  $('abandoned').textContent=o.queued_abandoned;
  $('answerRate').textContent=pct(o.queued_answer_rate);
  $('abandonRate').textContent=pct(o.queued_abandon_rate);
  $('avgWait').textContent=wait(o.avg_queued_wait_seconds);
  $('peakHour').textContent=o.peak_hour?.label||'—';
  $('peakHourFoot').textContent=o.peak_hour?`${o.peak_hour.inbound} inbound interactions`:'No activity';
}

function renderHourly(rows){
  const max=Math.max(1,...rows.map(r=>r.inbound));
  $('hourlyBars').innerHTML=rows.map(r=>{
    const h=Math.max(r.inbound?4:0,r.inbound/max*210);
    const a=Math.max(r.abandoned?4:0,r.abandoned/max*210);
    return `<div class="bar-col" title="${r.label}: ${r.inbound} inbound, ${r.abandoned} abandoned">
      <div class="bar-value">${r.inbound||''}</div>
      <div class="bar-stack"><div class="bar-in" style="height:${h}px"></div><div class="bar-ab" style="height:${a}px"></div></div>
      <div class="bar-label">${r.label.replace(' ','')}</div>
    </div>`;
  }).join('');
}

function renderDaily(rows){
  if(!rows.length){$('dailyTrend').innerHTML='<div class="message">No daily data.</div>';return}
  const max=Math.max(1,...rows.map(r=>r.inbound));
  $('dailyTrend').innerHTML=rows.map(r=>`<div class="trend-row">
    <div><strong>${esc(r.day_name.slice(0,3))}</strong><div class="panel-meta">${esc(r.date)}</div></div>
    <div class="trend-track"><div class="trend-fill" style="width:${r.inbound/max*100}%"></div></div>
    <div style="text-align:right"><strong>${r.inbound}</strong><div class="panel-meta">${pct(r.answer_rate)} ans</div></div>
  </div>`).join('');
}

function renderQueues(){
  const rows=[...(data?.queues||[])].sort((a,b)=>{
    const av=a[sortKey],bv=b[sortKey];
    if(typeof av==='string'||typeof bv==='string')return String(av??'').localeCompare(String(bv??''))*sortDir;
    return (Number(av||0)-Number(bv||0))*sortDir;
  });
  $('queueMeta').textContent=`${rows.length} queue groups`;
  $('queueBody').innerHTML=rows.map(r=>{
    const cls=r.queue_name==='Unassigned / No Queue'?'warn':(r.abandon_rate>=20?'bad':'good');
    return `<tr>
      <td class="queue-name"><span class="pill ${cls}">${esc(r.queue_name)}</span></td>
      <td>${r.offered}</td><td>${r.answered}</td><td>${r.abandoned}</td>
      <td>${pct(r.answer_rate)}</td><td>${pct(r.abandon_rate)}</td>
      <td>${wait(r.avg_queue_seconds)}</td><td>${wait(r.max_queue_seconds)}</td>
    </tr>`;
  }).join('');
}

async function load(){
  $('page').classList.add('loading');
  try{
    const r=await fetch(url()); if(!r.ok)throw new Error(`HTTP ${r.status}`);
    data=await r.json();
    renderOverview(data.overview);renderHourly(data.hourly);renderDaily(data.daily);renderQueues();
    $('version').textContent=`Backend v${data.backend_version}`;
  }catch(e){
    document.querySelector('.grid2').innerHTML=`<div class="panel"><div class="message">Could not load Call Demand data: ${esc(e.message)}</div></div>`;
  }finally{$('page').classList.remove('loading')}
}
document.querySelectorAll('th[data-sort]').forEach(th=>th.addEventListener('click',()=>{const k=th.dataset.sort;if(sortKey===k)sortDir*=-1;else{sortKey=k;sortDir=(k==='queue_name'?1:-1)}renderQueues()}));
$('applyBtn').addEventListener('click',load);
const modal=$('modal');$('infoBtn').addEventListener('click',()=>modal.classList.add('open'));$('closeBtn').addEventListener('click',()=>modal.classList.remove('open'));modal.addEventListener('click',e=>{if(e.target===modal)modal.classList.remove('open')});document.addEventListener('keydown',e=>{if(e.key==='Escape')modal.classList.remove('open')});
load();
</script>
</body>
</html>
    """

