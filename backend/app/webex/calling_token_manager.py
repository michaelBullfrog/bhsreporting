from __future__ import annotations

import time
from dataclasses import dataclass
import httpx
from ..config import settings

class CallingTokenRefreshError(RuntimeError):
    pass

@dataclass
class CallingTokenState:
    access_token: str
    refresh_token: str
    expires_at: float

class CallingTokenManager:
    def __init__(self):
        self.state = CallingTokenState(
            access_token=settings.webex_calling_access_token or "",
            refresh_token=settings.webex_calling_refresh_token or "",
            expires_at=0,
        )

    def has_refresh_credentials(self):
        return bool(settings.webex_calling_client_id and settings.webex_calling_client_secret and self.state.refresh_token)

    def _refresh(self):
        if not self.has_refresh_credentials():
            if self.state.access_token:
                return self.state
            raise CallingTokenRefreshError("No Webex Calling Service App token configured.")
        data={
            "grant_type":"refresh_token",
            "client_id":settings.webex_calling_client_id,
            "client_secret":settings.webex_calling_client_secret,
            "refresh_token":self.state.refresh_token,
        }
        with httpx.Client(timeout=30) as client:
            resp=client.post(settings.webex_calling_token_url,data=data,headers={"Accept":"application/json"})
        if resp.status_code >= 400:
            raise CallingTokenRefreshError(f"Calling token refresh HTTP {resp.status_code}: {resp.text}")
        body=resp.json()
        access=body.get("access_token")
        if not access:
            raise CallingTokenRefreshError(f"Calling token response missing access_token: {body}")
        self.state=CallingTokenState(
            access_token=access,
            refresh_token=body.get("refresh_token") or self.state.refresh_token,
            expires_at=time.time()+max(int(body.get("expires_in",3600))-120,60),
        )
        return self.state

    def get_access_token(self, force_refresh=False):
        if self.has_refresh_credentials():
            if force_refresh or not self.state.access_token or time.time() >= self.state.expires_at:
                self._refresh()
            return self.state.access_token
        if self.state.access_token:
            return self.state.access_token
        raise CallingTokenRefreshError("No Webex Calling access token configured.")

calling_token_manager=CallingTokenManager()
