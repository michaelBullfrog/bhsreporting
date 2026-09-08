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


async def _fix_call_demand_queue_filter(response):
    """Fix the Call Demand page so the selected queue is sent to the API."""
    return await _rewrite_html_response(
        response,
        lambda text: text.replace(
            _CALL_DEMAND_BROKEN_URL_SNIPPET,
            _CALL_DEMAND_FIXED_URL_SNIPPET,
            1,
        ),
    )


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
