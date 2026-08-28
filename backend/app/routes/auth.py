import base64
import hashlib
import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..auth_config import get_auth_settings


router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("webex-auth")

AUTHORIZE_URL = "https://webexapis.com/v1/authorize"
TOKEN_URL = "https://webexapis.com/v1/access_token"
PEOPLE_ME_URL = "https://webexapis.com/v1/people/me"


def _safe_next(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/executive-overview"
    return value


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _email_and_domain(person: dict) -> tuple[str, str]:
    emails = person.get("emails") or []
    email = str(emails[0]).strip().lower() if emails else ""
    domain = email.rsplit("@", 1)[1] if "@" in email else ""
    return email, domain


def _authorized(person: dict, settings) -> tuple[bool, str]:
    email, domain = _email_and_domain(person)
    org_id = str(person.get("orgId") or "").strip().lower()

    # Fail closed if there are no authorization rules.
    if not (
        settings.allowed_org_ids
        or settings.allowed_emails
        or settings.allowed_domains
    ):
        return False, "No authorization rules are configured."

    # If an org allowlist is configured, the user's Webex org MUST match it.
    if settings.allowed_org_ids and org_id not in settings.allowed_org_ids:
        return False, "Webex organization is not authorized."

    # If email/domain rules are configured, the user MUST match at least one.
    identity_rules_configured = bool(
        settings.allowed_emails or settings.allowed_domains
    )
    identity_match = (
        email in settings.allowed_emails
        or domain in settings.allowed_domains
    )
    if identity_rules_configured and not identity_match:
        return False, "Webex identity is not authorized."

    return True, "authorized"


def _shell(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | BHS Corrugated</title>
<style>
:root{{--bg:#f4f7fa;--ink:#12263a;--muted:#667788;--line:#d8e2ec;--brand:#0a5fa8;--dark:#063b66}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink)}}
.top{{height:72px;background:var(--dark);display:flex;align-items:center;justify-content:space-between;padding:0 28px}}
.top strong{{color:#fff;font-size:16px}}.logo{{background:#fff;border-radius:8px;padding:5px 10px;height:50px;display:flex;align-items:center}}
.logo img{{height:38px;width:auto;display:block}}
.wrap{{min-height:calc(100vh - 72px);display:grid;place-items:center;padding:28px}}
.card{{width:min(520px,100%);background:#fff;border:1px solid var(--line);border-radius:18px;padding:30px;box-shadow:0 12px 34px rgba(0,63,115,.10)}}
h1{{margin:0 0 8px;font-size:28px}}p{{color:var(--muted);line-height:1.55}}.btn{{display:inline-flex;align-items:center;justify-content:center;text-decoration:none;border:0;border-radius:10px;background:var(--brand);color:#fff;padding:12px 18px;font-weight:800;margin-top:10px}}
.small{{font-size:12px;color:var(--muted);margin-top:18px}}code{{background:#eef4f8;border-radius:5px;padding:2px 5px}}
ul{{color:var(--muted);line-height:1.8}}
</style>
</head>
<body>
<div class="top"><strong>BHS Corrugated · Contact Center Analytics</strong><div class="logo"><img src="/static/bhs_logo.png" alt="BHS Corrugated"></div></div>
<div class="wrap"><div class="card">{body}</div></div>
</body>
</html>""",
        status_code=status_code,
    )


@router.get("/login", response_class=HTMLResponse)
def login(next: str = "/executive-overview"):
    settings = get_auth_settings()
    if not settings.enabled:
        return RedirectResponse(_safe_next(next), status_code=302)
    if not settings.configured:
        return RedirectResponse("/auth/setup-required", status_code=302)

    target = _safe_next(next)
    return _shell(
        "Sign in",
        f"""
        <h1>Sign in required</h1>
        <p>Use your Webex account to access the BHS Corrugated Contact Center Analytics dashboard.</p>
        <a class="btn" href="/auth/webex?next={target}">Sign in with Webex</a>
        <div class="small">Access is limited to identities authorized by the dashboard administrator.</div>
        """,
    )


@router.get("/webex")
def start_webex_login(request: Request, next: str = "/executive-overview"):
    settings = get_auth_settings()
    if not settings.enabled:
        return RedirectResponse(_safe_next(next), status_code=302)
    if not settings.configured:
        return RedirectResponse("/auth/setup-required", status_code=302)

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)

    request.session["oauth_state"] = state
    request.session["oauth_verifier"] = verifier
    request.session["oauth_nonce"] = nonce
    request.session["oauth_next"] = _safe_next(next)

    params = {
        "client_id": settings.client_id,
        "response_type": "code",
        "redirect_uri": settings.redirect_uri,
        "scope": settings.scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    return RedirectResponse(
        f"{AUTHORIZE_URL}?{urlencode(params)}",
        status_code=302,
    )


@router.get("/webex/callback")
async def webex_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    settings = get_auth_settings()
    if error:
        return _shell(
            "Sign in failed",
            f"<h1>Webex sign-in failed</h1><p>{error_description or error}</p>"
            '<a class="btn" href="/auth/login">Try again</a>',
            400,
        )

    expected_state = request.session.pop("oauth_state", None)
    verifier = request.session.pop("oauth_verifier", None)
    request.session.pop("oauth_nonce", None)
    target = _safe_next(request.session.pop("oauth_next", None))

    if not code or not state or not expected_state or state != expected_state:
        return _shell(
            "Sign in failed",
            "<h1>Sign in could not be verified</h1><p>The Webex login state did not match. Please try again.</p>"
            '<a class="btn" href="/auth/login">Try again</a>',
            400,
        )
    if not verifier:
        return _shell(
            "Sign in failed",
            "<h1>Sign in session expired</h1><p>Please start the Webex sign-in again.</p>"
            '<a class="btn" href="/auth/login">Try again</a>',
            400,
        )

    async with httpx.AsyncClient(timeout=20.0) as client:
        token_response = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.client_id,
                "client_secret": settings.client_secret,
                "code": code,
                "redirect_uri": settings.redirect_uri,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )

        if token_response.status_code >= 400:
            log.warning(
                "Webex token exchange failed: HTTP %s %s",
                token_response.status_code,
                token_response.text[:500],
            )
            return _shell(
                "Sign in failed",
                "<h1>Webex token exchange failed</h1><p>Please try again or contact the dashboard administrator.</p>"
                '<a class="btn" href="/auth/login">Try again</a>',
                502,
            )

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return _shell(
                "Sign in failed",
                "<h1>Webex did not return an access token</h1><p>Please contact the dashboard administrator.</p>",
                502,
            )

        person_response = await client.get(
            PEOPLE_ME_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

    if person_response.status_code >= 400:
        log.warning(
            "Webex people/me failed: HTTP %s %s",
            person_response.status_code,
            person_response.text[:500],
        )
        return _shell(
            "Sign in failed",
            "<h1>Could not verify your Webex identity</h1><p>Confirm the integration includes the required People read scope.</p>",
            502,
        )

    person = person_response.json()
    email, _ = _email_and_domain(person)
    org_id = str(person.get("orgId") or "").strip()

    allowed, reason = _authorized(person, settings)
    if not allowed:
        log.warning(
            "Denied Webex dashboard login email=%s org_id=%s reason=%s",
            email or "-",
            org_id or "-",
            reason,
        )
        request.session.clear()
        return _shell(
            "Access denied",
            "<h1>Access denied</h1><p>Your Webex account authenticated successfully, but it is not authorized for this dashboard.</p>"
            "<p>Please contact the dashboard administrator if you believe you should have access.</p>",
            403,
        )

    request.session.clear()
    request.session["user"] = {
        "id": person.get("id"),
        "display_name": person.get("displayName"),
        "email": email,
        "org_id": org_id,
    }

    log.info(
        "Authorized Webex dashboard login email=%s org_id=%s",
        email or "-",
        org_id or "-",
    )
    return RedirectResponse(target, status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=302)


@router.get("/me")
def me(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {"authenticated": True, "user": user}


@router.get("/setup-required", response_class=HTMLResponse)
def setup_required():
    settings = get_auth_settings()
    missing = settings.missing_required_settings
    if not settings.enabled:
        return _shell(
            "Authentication disabled",
            "<h1>Webex authentication is disabled</h1><p>Set <code>WEBEX_AUTH_ENABLED=true</code> to require sign-in.</p>",
        )

    items = "".join(f"<li><code>{item}</code></li>" for item in missing)
    return _shell(
        "Authentication setup required",
        f"""
        <h1>Authentication setup required</h1>
        <p>The dashboard is locked until Webex authentication is fully configured.</p>
        <p>Missing configuration:</p>
        <ul>{items or "<li>Unknown configuration issue</li>"}</ul>
        <div class="small">The dashboard fails closed so analytics are not exposed without authentication.</div>
        """,
        503,
    )
