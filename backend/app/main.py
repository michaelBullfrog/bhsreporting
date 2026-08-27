from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from .database import Base, engine
from .routes.health import router as health_router
from .routes.collector import router as collector_router
from .routes.dashboard import router as dashboard_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="WxCC Analytics",
    version="0.1.0",
    description="Render-hosted Webex Contact Center analytics collector and dashboard API.",
)

app.include_router(health_router)
app.include_router(collector_router)
app.include_router(dashboard_router)

@app.get("/", response_class=HTMLResponse)
def home():
    return '''
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>WxCC Analytics</title>
      <style>
        body { font-family: Arial, sans-serif; max-width: 1100px; margin: 40px auto; padding: 0 20px; background:#f5f7fa; color:#111827; }
        h1 { margin-bottom: 4px; }
        .muted { color:#6b7280; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-top:24px; }
        .card { background:white; border-radius:12px; padding:18px; box-shadow:0 1px 4px rgba(0,0,0,.08); }
        .value { font-size:28px; font-weight:700; }
        pre { background:#111827; color:#e5e7eb; padding:16px; border-radius:10px; overflow:auto; }
      </style>
    </head>
    <body>
      <h1>WxCC Analytics</h1>
      <div class="muted">Phase 1 collector + database validation dashboard</div>
      <div id="cards" class="grid"></div>
      <h2>Data Health</h2>
      <pre id="health">Loading...</pre>
      <script>
        async function load() {
          const o = await fetch('/api/dashboard/overview').then(r => r.json());
          const h = await fetch('/api/data-health').then(r => r.json());
          const fields = [
            ['Total', o.total_interactions],
            ['Inbound', o.inbound],
            ['Outdial', o.outdial],
            ['Answered', o.answered],
            ['Abandoned', o.abandoned],
            ['Answer Rate', o.answer_rate + '%'],
            ['Abandon Rate', o.abandon_rate + '%'],
            ['Avg Queue', o.avg_queue_seconds + 's'],
            ['Max Queue', o.max_queue_seconds + 's'],
            ['Native Callbacks', o.successful_native_callbacks],
          ];
          document.getElementById('cards').innerHTML = fields.map(([k,v]) =>
            `<div class="card"><div class="muted">${k}</div><div class="value">${v}</div></div>`
          ).join('');
          document.getElementById('health').textContent = JSON.stringify(h, null, 2);
        }
        load();
      </script>
    </body>
    </html>
    '''
