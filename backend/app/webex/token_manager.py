from __future__ import annotations

from dataclasses import dataclass
import time
import httpx

from ..config import settings


class TokenRefreshError(RuntimeError):
    pass


@dataclass
class TokenState:
    access_token: str
    refresh_token: str
    expires_at: float


class TokenManager:
    """
    In-memory token cache for a running process.

    Render cron jobs start a fresh process each run, so each job can refresh
    using WXCC_REFRESH_TOKEN before calling WxCC. If Cisco rotates the refresh
    token, the new token is returned to the caller and logged, but Render env
    vars cannot be updated automatically by this app without adding a secret
    store/Render API integration.

    For production, keep the current refresh token in a secure secret store.
    """

    def __init__(self):
        self.state = TokenState(
            access_token=settings.wxcc_access_token or "",
            refresh_token=settings.wxcc_refresh_token or "",
            expires_at=0,
        )

    def has_refresh_credentials(self) -> bool:
        return bool(
            settings.wxcc_client_id
            and settings.wxcc_client_secret
            and self.state.refresh_token
        )

    def _refresh(self) -> TokenState:
        if not self.has_refresh_credentials():
            if self.state.access_token:
                return self.state
            raise TokenRefreshError(
                "No usable WxCC token. Set WXCC_ACCESS_TOKEN or "
                "WXCC_CLIENT_ID/WXCC_CLIENT_SECRET/WXCC_REFRESH_TOKEN."
            )

        data = {
            "grant_type": "refresh_token",
            "client_id": settings.wxcc_client_id,
            "client_secret": settings.wxcc_client_secret,
            "refresh_token": self.state.refresh_token,
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                settings.wxcc_token_url,
                data=data,
                headers={"Accept": "application/json"},
            )

        if resp.status_code >= 400:
            raise TokenRefreshError(
                f"Token refresh HTTP {resp.status_code}: {resp.text}"
            )

        body = resp.json()
        access_token = body.get("access_token")
        refresh_token = body.get("refresh_token") or self.state.refresh_token
        expires_in = int(body.get("expires_in", 3600))

        if not access_token:
            raise TokenRefreshError(
                f"Token response did not include access_token: {body}"
            )

        self.state = TokenState(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + max(expires_in - 120, 60),
        )
        return self.state

    def get_access_token(self, force_refresh: bool = False) -> str:
        # If refresh credentials exist, prefer a refreshed token for scheduled jobs.
        if self.has_refresh_credentials():
            if force_refresh or not self.state.access_token or time.time() >= self.state.expires_at:
                self._refresh()
            return self.state.access_token

        if self.state.access_token:
            return self.state.access_token

        raise TokenRefreshError("No WxCC access token configured.")

    def force_refresh(self) -> str:
        return self._refresh().access_token


token_manager = TokenManager()
