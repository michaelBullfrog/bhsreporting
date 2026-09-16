from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import httpx
from sqlalchemy import text

from ..config import settings
from ..database import Base, SessionLocal, engine
from ..models import WxccOAuthToken


class TokenRefreshError(RuntimeError):
    pass


@dataclass
class TokenState:
    access_token: str
    refresh_token: str
    expires_at: datetime | None


class TokenManager:
    """Shared PostgreSQL-backed token manager for WxCC scheduled jobs.

    Render cron jobs start in fresh processes. The database is therefore the
    authoritative token store after the first bootstrap from Render env vars.
    A PostgreSQL advisory transaction lock prevents collector/reconcile jobs
    from refreshing the same token pair at the same time.
    """

    TOKEN_KEY = "wxcc"
    ADVISORY_LOCK_ID = 914267301
    REFRESH_EARLY_SECONDS = 300

    def __init__(self):
        # Cron jobs do not necessarily start the FastAPI app, so ensure the
        # shared token table exists before trying to read it.
        Base.metadata.create_all(bind=engine, tables=[WxccOAuthToken.__table__])
        self._last_access_token = ""

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _state_from_row(self, row: WxccOAuthToken) -> TokenState:
        return TokenState(
            access_token=row.access_token or "",
            refresh_token=row.refresh_token or "",
            expires_at=self._aware(row.expires_at),
        )

    def _load_or_seed(self, db) -> TokenState:
        row = db.get(WxccOAuthToken, self.TOKEN_KEY)
        env_access = settings.wxcc_access_token or ""
        env_refresh = settings.wxcc_refresh_token or ""

        if row:
            # Environment values are bootstrap/fallback only. Never overwrite a
            # token that has already rotated in PostgreSQL, but allow a missing
            # field to be filled later (for example after WXCC_REFRESH_TOKEN is
            # temporarily blanked during recovery from tokenlimit_reached).
            changed = False
            if not row.access_token and env_access:
                row.access_token = env_access
                changed = True
            if not row.refresh_token and env_refresh:
                row.refresh_token = env_refresh
                changed = True
            if changed:
                row.updated_at = self._utcnow()
                db.flush()
            return self._state_from_row(row)

        if not env_access and not env_refresh:
            raise TokenRefreshError(
                "No shared WxCC token exists and no bootstrap token is configured. "
                "Set WXCC_ACCESS_TOKEN and, for automatic renewal, WXCC_REFRESH_TOKEN."
            )

        # The actual expiry of a bootstrap access token is not available from
        # Render env alone. Leave it unknown and use it until WxCC returns an
        # auth failure. Once refreshed, expires_at is persisted from expires_in.
        row = WxccOAuthToken(
            token_key=self.TOKEN_KEY,
            access_token=env_access or None,
            refresh_token=env_refresh or None,
            expires_at=None,
            updated_at=self._utcnow(),
        )
        db.add(row)
        db.flush()
        return self._state_from_row(row)

    def _load_state(self) -> TokenState:
        db = SessionLocal()
        try:
            state = self._load_or_seed(db)
            db.commit()
            return state
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def has_refresh_credentials(self) -> bool:
        if not (settings.wxcc_client_id and settings.wxcc_client_secret):
            return False
        try:
            return bool(self._load_state().refresh_token)
        except TokenRefreshError:
            return bool(settings.wxcc_refresh_token)

    def _needs_refresh(self, state: TokenState) -> bool:
        if not state.access_token:
            return True
        if state.expires_at is None:
            return False
        return self._utcnow() >= state.expires_at - timedelta(
            seconds=self.REFRESH_EARLY_SECONDS
        )

    def _request_refresh(self, refresh_token: str) -> tuple[str, str, datetime]:
        if not (
            settings.wxcc_client_id
            and settings.wxcc_client_secret
            and refresh_token
        ):
            raise TokenRefreshError(
                "WxCC token needs renewal but refresh credentials are unavailable."
            )

        data = {
            "grant_type": "refresh_token",
            "client_id": settings.wxcc_client_id,
            "client_secret": settings.wxcc_client_secret,
            "refresh_token": refresh_token,
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
        next_refresh_token = body.get("refresh_token") or refresh_token
        expires_in = int(body.get("expires_in", 3600))

        if not access_token:
            raise TokenRefreshError(
                "Token refresh response did not include an access_token."
            )

        expires_at = self._utcnow() + timedelta(seconds=max(expires_in, 60))
        return access_token, next_refresh_token, expires_at

    def _refresh_under_lock(self, failed_access_token: str = "") -> TokenState:
        db = SessionLocal()
        try:
            # Transaction-scoped lock. It remains held through the token refresh
            # and DB update, then releases automatically on commit/rollback.
            db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": self.ADVISORY_LOCK_ID},
            )

            state = self._load_or_seed(db)

            # If another process refreshed while this process was waiting for
            # the lock, use the newer DB token instead of creating another one.
            if (
                failed_access_token
                and state.access_token
                and state.access_token != failed_access_token
            ):
                db.commit()
                return state

            access_token, refresh_token, expires_at = self._request_refresh(
                state.refresh_token
            )

            row = db.get(WxccOAuthToken, self.TOKEN_KEY)
            row.access_token = access_token
            row.refresh_token = refresh_token
            row.expires_at = expires_at
            row.updated_at = self._utcnow()
            db.commit()

            return TokenState(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_access_token(self, force_refresh: bool = False) -> str:
        state = self._load_state()

        if force_refresh:
            state = self._refresh_under_lock(
                failed_access_token=self._last_access_token
            )
        elif self._needs_refresh(state):
            state = self._refresh_under_lock()

        if not state.access_token:
            raise TokenRefreshError("No WxCC access token configured.")

        self._last_access_token = state.access_token
        return state.access_token

    def force_refresh(self) -> str:
        state = self._refresh_under_lock(
            failed_access_token=self._last_access_token
        )
        self._last_access_token = state.access_token
        return state.access_token


token_manager = TokenManager()
