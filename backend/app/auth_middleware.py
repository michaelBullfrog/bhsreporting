from urllib.parse import quote

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .auth_config import get_auth_settings


PUBLIC_PREFIXES = (
    "/auth",
    "/static",
)

PUBLIC_EXACT = {
    "/api/health",
    "/favicon.ico",
}


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
            return await call_next(request)

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
