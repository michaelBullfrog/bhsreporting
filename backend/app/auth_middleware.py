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


async def _remove_staffing_queue_filter(response):
    """Presentation-only cleanup for the Staffing page.

    The Staffing report is agent/session based, so a queue selector is not
    appropriate there. The existing page JavaScript already treats a missing
    queueFilter element as optional, so removing this control is safe and does
    not change the staffing API or calculations.
    """
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type.lower():
        return response

    body = b"".join([chunk async for chunk in response.body_iterator])
    text = body.decode("utf-8")

    if _STAFFING_QUEUE_FILTER_HTML not in text:
        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
            background=response.background,
        )

    text = text.replace(_STAFFING_QUEUE_FILTER_HTML, "", 1)

    headers = dict(response.headers)
    headers.pop("content-length", None)

    return Response(
        content=text,
        status_code=response.status_code,
        headers=headers,
        media_type="text/html",
        background=response.background,
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
