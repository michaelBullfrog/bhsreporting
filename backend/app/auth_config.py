from dataclasses import dataclass
import os


def _csv(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {
        item.strip().lower()
        for item in raw.split(",")
        if item.strip()
    }


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WebexAuthSettings:
    enabled: bool
    client_id: str
    client_secret: str
    redirect_uri: str
    session_secret: str
    session_hours: int
    allowed_org_ids: set[str]
    allowed_emails: set[str]
    allowed_domains: set[str]
    scopes: str

    @property
    def missing_required_settings(self) -> list[str]:
        missing = []
        if not self.client_id:
            missing.append("WEBEX_AUTH_CLIENT_ID")
        if not self.client_secret:
            missing.append("WEBEX_AUTH_CLIENT_SECRET")
        if not self.redirect_uri:
            missing.append("WEBEX_AUTH_REDIRECT_URI")
        if not self.session_secret:
            missing.append("WEBEX_AUTH_SESSION_SECRET")
        if not (
            self.allowed_org_ids
            or self.allowed_emails
            or self.allowed_domains
        ):
            missing.append(
                "one authorization rule: WEBEX_AUTH_ALLOWED_ORG_IDS, "
                "WEBEX_AUTH_ALLOWED_EMAILS, or WEBEX_AUTH_ALLOWED_DOMAINS"
            )
        return missing

    @property
    def configured(self) -> bool:
        return not self.missing_required_settings


def get_auth_settings() -> WebexAuthSettings:
    try:
        session_hours = int(os.getenv("WEBEX_AUTH_SESSION_HOURS", "8"))
    except ValueError:
        session_hours = 8

    return WebexAuthSettings(
        enabled=_bool("WEBEX_AUTH_ENABLED", True),
        client_id=os.getenv("WEBEX_AUTH_CLIENT_ID", "").strip(),
        client_secret=os.getenv("WEBEX_AUTH_CLIENT_SECRET", "").strip(),
        redirect_uri=os.getenv("WEBEX_AUTH_REDIRECT_URI", "").strip(),
        session_secret=os.getenv("WEBEX_AUTH_SESSION_SECRET", "").strip(),
        session_hours=max(1, min(session_hours, 72)),
        allowed_org_ids=_csv("WEBEX_AUTH_ALLOWED_ORG_IDS"),
        allowed_emails=_csv("WEBEX_AUTH_ALLOWED_EMAILS"),
        allowed_domains=_csv("WEBEX_AUTH_ALLOWED_DOMAINS"),
        scopes=os.getenv(
            "WEBEX_AUTH_SCOPES",
            "openid email profile spark:people_read",
        ).strip(),
    )
