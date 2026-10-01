from urllib.parse import quote

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .auth_config import get_auth_settings


PUBLIC_PREFIXES = (
    "/auth",
    "/static",
)

PUBLIC_EXACT = {
    "/api/health",
    "/favicon.ico",
}


_STAFFING_QUEUE_FILTER_HTML = (
    '<div class="field"><label for="queueFilter">Queue</label>'
    '<select id="queueFilter"><option value="">All queues</option></select></div>'
)

_CALL_DEMAND_BROKEN_URL_SNIPPET = (
    "    const qf=$('queueFilter')?.value;if(qf)p.set('queue_name',qf);\n"
    "function url(){const p=new URLSearchParams();const f=localStart($('fromDate').value),t=localAfter($('toDate').value);if(f!==null)p.set('from_ms',f);if(t!==null)p.set('to_ms',t);p.set('timezone',Intl.DateTimeFormat().resolvedOptions().timeZone||'America/Detroit');return '/api/dashboard/call-demand?'+p.toString()}"
)

_CALL_DEMAND_FIXED_URL_SNIPPET = (
    "function url(){const p=new URLSearchParams();const f=localStart($('fromDate').value),t=localAfter($('toDate').value);if(f!==null)p.set('from_ms',f);if(t!==null)p.set('to_ms',t);p.set('timezone',Intl.DateTimeFormat().resolvedOptions().timeZone||'America/Detroit');const qf=$('queueFilter')?.value;if(qf)p.set('queue_name',qf);p.set('include_quick_calls',window.bhsIncludeQuickCalls!==false?'true':'false');return '/api/dashboard/call-demand?'+p.toString()}"
)

_EXECUTIVE_BROKEN_URL_SNIPPET = (
    "    const qf=$('queueFilter')?.value;if(qf)p.set('queue_name',qf);\n"
    "function apiUrl(){const p=new URLSearchParams(),f=localStart($('fromDate').value),t=localAfter($('toDate').value);if(f!==null)p.set('from_ms',f);if(t!==null)p.set('to_ms',t);p.set('timezone',Intl.DateTimeFormat().resolvedOptions().timeZone||'America/Detroit');return '/api/dashboard/executive-overview?'+p.toString()}"
)

_EXECUTIVE_FIXED_URL_SNIPPET = (
    "function apiUrl(){const p=new URLSearchParams(),f=localStart($('fromDate').value),t=localAfter($('toDate').value);if(f!==null)p.set('from_ms',f);if(t!==null)p.set('to_ms',t);p.set('timezone',Intl.DateTimeFormat().resolvedOptions().timeZone||'America/Detroit');const qf=$('queueFilter')?.value;if(qf)p.set('queue_name',qf);p.set('include_quick_calls',window.bhsIncludeQuickCalls!==false?'true':'false');return '/api/dashboard/executive-overview?'+p.toString()}"
)

_MISSED_CALLBACKS_MASKED_PHONE = r"""function phone(v){
  const d=String(v||'').replace(/\D/g,'');
  const x=d.length>10?d.slice(-10):d;
  if(x.length!==10)return v||'—';
  return `(***) ***-${x.slice(-4)}`;
}"""

_MISSED_CALLBACKS_FULL_PHONE = r"""function phone(v){
  const raw=String(v||'').trim();
  if(!raw)return '—';
  const d=raw.replace(/\D/g,'');
  const x=d.length===11&&d.startsWith('1')?d.slice(1):d;
  if(x.length===10)return `(${x.slice(0,3)}) ${x.slice(3,6)}-${x.slice(6)}`;
  if(d.length===11&&d.startsWith('1'))return `+1 (${d.slice(1,4)}) ${d.slice(4,7)}-${d.slice(7)}`;
  return raw;
}"""

_QUICK_CALL_TOGGLE = r"""
<style>
.quick-call-toggle-wrap{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 14px;padding:10px 14px;background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}
.quick-call-toggle-label{font-size:12px;font-weight:850;color:var(--ink)}
.quick-call-toggle-note{font-size:11px;color:var(--muted)}
.quick-call-toggle{border:1px solid #b8c9d6;border-radius:999px;padding:7px 12px;background:#eef4f8;color:#35566e;font-size:12px;font-weight:850;cursor:pointer}
.quick-call-toggle.excluding{background:#fff3e8;color:#8a4b00;border-color:#e5bd8c}
</style>
<script>
(function(){
  window.bhsIncludeQuickCalls = true;
  function render(){
    const b=document.getElementById('quickCallToggle');
    if(!b)return;
    const including=window.bhsIncludeQuickCalls!==false;
    b.textContent=including?'Quick Calls: Included':'Quick Calls: Excluded';
    b.classList.toggle('excluding',!including);
    b.setAttribute('aria-pressed',including?'false':'true');
  }
  function triggerReload(){
    if(typeof load==='function'){load();return;}
    if(typeof loadData==='function'){loadData();return;}
    const apply=document.getElementById('applyBtn');
    if(apply){apply.click();return;}
    const buttons=[...document.querySelectorAll('button')];
    const btn=buttons.find(x=>/apply|refresh/i.test(x.textContent||''));
    if(btn)btn.click();
  }
  document.addEventListener('DOMContentLoaded',function(){
    const page=document.querySelector('.page')||document.querySelector('main');
    if(!page||document.getElementById('quickCallToggle'))return;
    const box=document.createElement('div');
    box.className='quick-call-toggle-wrap';
    box.innerHTML='<span class="quick-call-toggle-label">Statistical Call Filter</span><button id="quickCallToggle" class="quick-call-toggle" type="button"></button><span class="quick-call-toggle-note">Quick calls are task-level interactions under 10 seconds. Toggle them out to recalculate this page without those calls.</span>';
    const health=page.querySelector('.health-strip');
    const heading=page.querySelector('.heading-row');
    const anchor=health||heading||page.firstChild;
    if(anchor&&anchor.parentNode)anchor.parentNode.insertBefore(box,anchor.nextSibling);else page.prepend(box);
    render();
    document.getElementById('quickCallToggle').addEventListener('click',function(){
      window.bhsIncludeQuickCalls=window.bhsIncludeQuickCalls===false;
      render();
      triggerReload();
    });
  });
})();
</script>
"""

_CALL_DEMAND_QUEUED_CARD = (
    '<div class="kpi"><div class="kpi-label">Queued Inbound</div>'
    '<div class="kpi-value" id="queued">—</div>'
    '<div class="kpi-foot" id="unqueued">—</div></div>'
)

_CALL_DEMAND_SUMMARY_CARDS = (
    _CALL_DEMAND_QUEUED_CARD
    + '<div class="kpi"><div class="kpi-label">Non-Queued / IVR Outcomes</div>'
      '<div class="kpi-value" id="nonQueuedKpi">—</div>'
      '<div class="kpi-foot">never entered a queue</div></div>'
)

_CALL_DEMAND_ABANDONED_CARD = (
    '<div class="kpi"><div class="kpi-label">Abandoned</div>'
    '<div class="kpi-value" id="abandoned">—</div>'
    '<div class="kpi-foot">queued interactions</div></div>'
)

_CALL_DEMAND_ABANDONED_WITH_OUTBOUND = (
    _CALL_DEMAND_ABANDONED_CARD
    + '<div class="kpi"><div class="kpi-label">Outbound</div>'
      '<div class="kpi-value" id="outboundSummary">—</div>'
      '<div class="kpi-foot">separate outbound activity</div></div>'
)

_CALL_DEMAND_PANEL_TITLE = '<div class="panel-title">Non-Queued Inbound Outcomes</div>'
_CALL_DEMAND_PANEL_TITLE_UPDATED = '<div class="panel-title">Non-Queued / IVR Outcomes</div>'

_CALL_DEMAND_SUMMARY_SYNC = r"""
<style>
.call-demand-kpi-groups{display:grid;gap:16px;margin-bottom:20px}
.call-demand-kpi-group{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:var(--shadow)}
.call-demand-kpi-group-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-end;margin-bottom:12px;flex-wrap:wrap}
.call-demand-kpi-group-title{font-size:14px;font-weight:900;color:var(--ink)}
.call-demand-kpi-group-sub{font-size:12px;color:var(--muted);margin-top:3px;line-height:1.4}
.call-demand-kpi-group-grid{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px}
.call-demand-kpi-group.inbound-flow{border-left:4px solid #0a5fa8}
.call-demand-kpi-group.queue-results{border-left:4px solid #2e8b57}
.call-demand-kpi-group.supporting{border-left:4px solid #6d7f8f}
.call-demand-kpi-group .kpi{box-shadow:none;margin:0;background:#f9fbfd}
.call-demand-kpi-group.inbound-flow .kpi:first-child{background:#eef6fc}
.call-demand-kpi-group.queue-results .kpi:nth-child(1){background:#eff8f2}
.call-demand-kpi-group.queue-results .kpi:nth-child(2){background:#fff4f1}
.call-demand-flow-note{font-size:11px;color:var(--muted);font-weight:700}
@media(max-width:1000px){.call-demand-kpi-group-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:620px){.call-demand-kpi-group-grid{grid-template-columns:1fr}}
</style>
<script>
(function(){
  function cardByValueId(id){const el=document.getElementById(id);return el ? el.closest('.kpi') : null;}
  function makeGroup(cls,title,sub,ids){const cards=ids.map(cardByValueId).filter(Boolean);if(!cards.length)return null;const section=document.createElement('section');section.className='call-demand-kpi-group '+cls;const head=document.createElement('div');head.className='call-demand-kpi-group-head';head.innerHTML='<div><div class="call-demand-kpi-group-title">'+title+'</div><div class="call-demand-kpi-group-sub">'+sub+'</div></div>';const grid=document.createElement('div');grid.className='call-demand-kpi-group-grid';cards.forEach(c=>grid.appendChild(c));section.appendChild(head);section.appendChild(grid);return section;}
  function organizeBhsKpis(){if(document.querySelector('.call-demand-kpi-groups'))return;const original=document.querySelector('section.kpis');if(!original)return;const wrapper=document.createElement('div');wrapper.className='call-demand-kpi-groups';const inbound=makeGroup('inbound-flow','Inbound Call Flow','Every inbound interaction is either queued or handled outside the queue in IVR/routing.',['inbound','queued','nonQueuedKpi']);const results=makeGroup('queue-results','Queue Results','Only calls that entered a queue are included here. Queued Calls = Answered + Abandoned.',['answered','abandoned','answerRate','abandonRate']);const supporting=makeGroup('supporting','Supporting Activity & Wait','Additional context. Outbound is separate from inbound flow and does not belong inside queued results.',['outboundSummary','avgWait','maxWait','peakHour']);[inbound,results,supporting].forEach(g=>{if(g)wrapper.appendChild(g)});original.parentNode.insertBefore(wrapper,original);const supportingGrid=supporting?.querySelector('.call-demand-kpi-group-grid');if(supportingGrid){Array.from(original.querySelectorAll('.kpi')).forEach(card=>{if(card.style.display!=='none')supportingGrid.appendChild(card);});}original.style.display='none';}
  function syncBhsCallDemandSummary(){const sourceNonQueued=document.getElementById('nonQueuedCount');const targetNonQueued=document.getElementById('nonQueuedKpi');if(sourceNonQueued&&targetNonQueued){targetNonQueued.textContent=sourceNonQueued.textContent;}const sourceOutbound=document.getElementById('outbound');const targetOutbound=document.getElementById('outboundSummary');if(sourceOutbound&&targetOutbound){targetOutbound.textContent=sourceOutbound.textContent;const oldCard=sourceOutbound.closest('.kpi');if(oldCard){oldCard.style.display='none';}}}
  document.addEventListener('DOMContentLoaded',function(){syncBhsCallDemandSummary();organizeBhsKpis();const nonQueued=document.getElementById('nonQueuedCount');const outbound=document.getElementById('outbound');const observer=new MutationObserver(syncBhsCallDemandSummary);if(nonQueued){observer.observe(nonQueued,{childList:true,characterData:true,subtree:true});}if(outbound){observer.observe(outbound,{childList:true,characterData:true,subtree:true});}const apply=document.getElementById('applyBtn');if(apply){apply.addEventListener('click',function(){setTimeout(syncBhsCallDemandSummary,250);setTimeout(syncBhsCallDemandSummary,900);});}});
})();
</script>
"""


async def _rewrite_html_response(response, transform):
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type.lower():
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    text = body.decode("utf-8")
    updated = transform(text)
    if updated == text:
        return Response(content=body,status_code=response.status_code,headers=dict(response.headers),media_type=response.media_type,background=response.background)
    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(content=updated,status_code=response.status_code,headers=headers,media_type="text/html",background=response.background)


async def _remove_staffing_queue_filter(response):
    return await _rewrite_html_response(response,lambda text: text.replace(_STAFFING_QUEUE_FILTER_HTML, "", 1))


def _transform_call_demand(text: str) -> str:
    updated = text.replace(_CALL_DEMAND_BROKEN_URL_SNIPPET,_CALL_DEMAND_FIXED_URL_SNIPPET,1)
    updated = updated.replace(_CALL_DEMAND_QUEUED_CARD,_CALL_DEMAND_SUMMARY_CARDS,1)
    updated = updated.replace(_CALL_DEMAND_ABANDONED_CARD,_CALL_DEMAND_ABANDONED_WITH_OUTBOUND,1)
    updated = updated.replace(_CALL_DEMAND_PANEL_TITLE,_CALL_DEMAND_PANEL_TITLE_UPDATED,1)
    if "id=\"nonQueuedKpi\"" in updated and _CALL_DEMAND_SUMMARY_SYNC not in updated:
        updated = updated.replace("</body>",_CALL_DEMAND_SUMMARY_SYNC+"\n</body>",1)
    if "id=\"quickCallToggle\"" not in updated:
        updated = updated.replace("</body>",_QUICK_CALL_TOGGLE+"\n</body>",1)
    return updated


def _transform_executive(text: str) -> str:
    updated = text.replace(_EXECUTIVE_BROKEN_URL_SNIPPET,_EXECUTIVE_FIXED_URL_SNIPPET,1)
    if "id=\"quickCallToggle\"" not in updated:
        updated = updated.replace("</body>",_QUICK_CALL_TOGGLE+"\n</body>",1)
    return updated


def _transform_missed_callbacks(text: str) -> str:
    return text.replace(_MISSED_CALLBACKS_MASKED_PHONE,_MISSED_CALLBACKS_FULL_PHONE,1)


async def _fix_call_demand_queue_filter(response):
    return await _rewrite_html_response(response, _transform_call_demand)


async def _fix_executive_queue_filter(response):
    return await _rewrite_html_response(response, _transform_executive)


async def _show_full_callback_numbers(response):
    return await _rewrite_html_response(response, _transform_missed_callbacks)


class WebexAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        settings = get_auth_settings()
        if not settings.enabled:
            return await call_next(request)
        path = request.url.path
        if path in PUBLIC_EXACT or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
            return await call_next(request)
        if not settings.configured:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Webex authentication setup is incomplete.","missing": settings.missing_required_settings},status_code=503)
            return RedirectResponse("/auth/setup-required", status_code=302)
        user = request.session.get("user")
        if user:
            response = await call_next(request)
            if path == "/staffing":
                response = await _remove_staffing_queue_filter(response)
            elif path == "/call-demand":
                response = await _fix_call_demand_queue_filter(response)
            elif path == "/executive-overview":
                response = await _fix_executive_queue_filter(response)
            elif path == "/missed-callbacks":
                response = await _show_full_callback_numbers(response)
            return response
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Authentication required."},status_code=401)
        next_path = path
        if request.url.query:
            next_path += "?" + request.url.query
        return RedirectResponse("/auth/login?next=" + quote(next_path, safe="/?=&"),status_code=302)
