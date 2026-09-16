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
    "function url(){const p=new URLSearchParams();const f=localStart($('fromDate').value),t=localAfter($('toDate').value);if(f!==null)p.set('from_ms',f);if(t!==null)p.set('to_ms',t);p.set('timezone',Intl.DateTimeFormat().resolvedOptions().timeZone||'America/Detroit');const qf=$('queueFilter')?.value;if(qf)p.set('queue_name',qf);return '/api/dashboard/call-demand?'+p.toString()}"
)

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
      '<div class="kpi-foot">outdial interactions</div></div>'
)

_CALL_DEMAND_PANEL_TITLE = (
    '<div class="panel-title">Non-Queued Inbound Outcomes</div>'
)

_CALL_DEMAND_PANEL_TITLE_UPDATED = (
    '<div class="panel-title">Non-Queued / IVR Outcomes</div>'
)

_CALL_DEMAND_SUMMARY_SYNC = r"""
<style>
@media (min-width:1201px){
  .kpis{grid-template-columns:repeat(4,minmax(150px,1fr))!important;}
}
</style>
<script>
(function(){
  function syncBhsCallDemandSummary(){
    const sourceNonQueued=document.getElementById('nonQueuedCount');
    const targetNonQueued=document.getElementById('nonQueuedKpi');
    if(sourceNonQueued&&targetNonQueued){targetNonQueued.textContent=sourceNonQueued.textContent;}

    const sourceOutbound=document.getElementById('outbound');
    const targetOutbound=document.getElementById('outboundSummary');
    if(sourceOutbound&&targetOutbound){
      targetOutbound.textContent=sourceOutbound.textContent;
      const oldCard=sourceOutbound.closest('.kpi');
      if(oldCard){oldCard.style.display='none';}
    }
  }

  document.addEventListener('DOMContentLoaded',function(){
    syncBhsCallDemandSummary();
    const nonQueued=document.getElementById('nonQueuedCount');
    const outbound=document.getElementById('outbound');
    const observer=new MutationObserver(syncBhsCallDemandSummary);
    if(nonQueued){observer.observe(nonQueued,{childList:true,characterData:true,subtree:true});}
    if(outbound){observer.observe(outbound,{childList:true,characterData:true,subtree:true});}
    const apply=document.getElementById('applyBtn');
    if(apply){apply.addEventListener('click',function(){setTimeout(syncBhsCallDemandSummary,250);setTimeout(syncBhsCallDemandSummary,900);});}
  });
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
        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
            background=response.background,
        )

    headers = dict(response.headers)
    headers.pop("content-length", None)

    return Response(
        content=updated,
        status_code=response.status_code,
        headers=headers,
        media_type="text/html",
        background=response.background,
    )


async def _remove_staffing_queue_filter(response):
    """Presentation-only cleanup for the Staffing page."""
    return await _rewrite_html_response(
        response,
        lambda text: text.replace(_STAFFING_QUEUE_FILTER_HTML, "", 1),
    )


def _transform_call_demand(text: str) -> str:
    """Apply Call Demand presentation fixes without changing metric logic."""
    updated = text.replace(
        _CALL_DEMAND_BROKEN_URL_SNIPPET,
        _CALL_DEMAND_FIXED_URL_SNIPPET,
        1,
    )
    updated = updated.replace(
        _CALL_DEMAND_QUEUED_CARD,
        _CALL_DEMAND_SUMMARY_CARDS,
        1,
    )
    updated = updated.replace(
        _CALL_DEMAND_ABANDONED_CARD,
        _CALL_DEMAND_ABANDONED_WITH_OUTBOUND,
        1,
    )
    updated = updated.replace(
        _CALL_DEMAND_PANEL_TITLE,
        _CALL_DEMAND_PANEL_TITLE_UPDATED,
        1,
    )

    if "id=\"nonQueuedKpi\"" in updated and _CALL_DEMAND_SUMMARY_SYNC not in updated:
        updated = updated.replace(
            "</body>",
            _CALL_DEMAND_SUMMARY_SYNC + "\n</body>",
            1,
        )

    return updated


async def _fix_call_demand_queue_filter(response):
    """Apply Call Demand queue-filter and summary presentation fixes."""
    return await _rewrite_html_response(response, _transform_call_demand)


class WebexAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        settings = get_auth_settings()

        if not settings.enabled:
            return await call_next(request)

        path = request.url.path

        if path in PUBLIC_EXACT or any(
            path.startswith(prefix) for prefix in PUBLIC_PREFIXES
        ):
            return await call_next(request)

        if not settings.configured:
            if path.startswith("/api/"):
                return JSONResponse(
                    {
                        "detail": "Webex authentication setup is incomplete.",
                        "missing": settings.missing_required_settings,
                    },
                    status_code=503,
                )
            return RedirectResponse("/auth/setup-required", status_code=302)

        user = request.session.get("user")
        if user:
            response = await call_next(request)
            if path == "/staffing":
                response = await _remove_staffing_queue_filter(response)
            elif path == "/call-demand":
                response = await _fix_call_demand_queue_filter(response)
            return response

        if path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Authentication required."},
                status_code=401,
            )

        next_path = path
        if request.url.query:
            next_path += "?" + request.url.query

        return RedirectResponse(
            "/auth/login?next=" + quote(next_path, safe="/?=&"),
            status_code=302,
        )
