import os
import json
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User

# Google often returns previously-granted scopes (e.g. an old gmail.readonly
# grant that hasn't been revoked) in addition to the ones we request. oauthlib's
# default strict scope-equality check rejects that with "Scope has changed".
# Relax it so token exchange succeeds; we still store the actual granted scopes.
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth/google", tags=["google-auth"])

SCOPES = [
    "https://mail.google.com/",  # full Gmail access — required for batchDelete and batchModify
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
]

_REDIRECT_URI = "https://starfire-production-3ad8.up.railway.app/auth/google/callback"


def _flow(state: str = None):
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [_REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=_REDIRECT_URI,
        state=state,
    )
    return flow


@router.get("")
async def google_auth_start(telegram_id: str):
    """Redirect user to Google OAuth. telegram_id is passed as state."""
    if not settings.google_client_id:
        return HTMLResponse(
            "<h2>Google OAuth not configured.</h2>"
            "<p>Ask the bot admin to set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.</p>",
            status_code=503,
        )
    flow = _flow(state=telegram_id)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    return RedirectResponse(auth_url)


@router.get("/callback")
async def google_auth_callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error or not code or not state:
        return HTMLResponse(
            f"<h2>Authorization failed.</h2><p>{error or 'Missing code or state.'}</p>"
            "<p>Close this tab and try /connect_google again.</p>",
            status_code=400,
        )

    try:
        telegram_id = int(state)
    except ValueError:
        return HTMLResponse("<h2>Invalid state.</h2>", status_code=400)

    try:
        flow = _flow(state=state)
        flow.fetch_token(code=code)
        creds = flow.credentials
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or SCOPES),
        }
        token_json = json.dumps(token_data)
    except Exception as e:
        logger.error("google_oauth_callback_error", error=str(e))
        return HTMLResponse(
            f"<h2>Token exchange failed.</h2><p>{e}</p>",
            status_code=500,
        )

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            return HTMLResponse(
                "<h2>User not found.</h2><p>Send /start to the STARFIRE bot first.</p>",
                status_code=404,
            )
        user.google_token_json = token_json
        await session.commit()

    logger.info("google_oauth_success", telegram_id=telegram_id)
    return HTMLResponse(
        """<!DOCTYPE html><html><head><title>STARFIRE — Google Connected</title>
        <style>
          body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
               background:#000;color:#fff;display:flex;align-items:center;
               justify-content:center;min-height:100vh;margin:0;}
          .card{background:#111;border:1px solid #e63946;border-radius:12px;
                padding:40px;max-width:420px;text-align:center;}
          h2{color:#e63946;margin:0 0 12px;}
          p{color:#aaa;margin:8px 0;}
          .badge{background:#e63946;color:#fff;border-radius:6px;
                 padding:4px 12px;font-size:13px;display:inline-block;margin-top:16px;}
        </style></head><body>
        <div class="card">
          <h2>✓ Google Connected</h2>
          <p>Gmail, Drive, Calendar, and Sheets are now linked to STARFIRE.</p>
          <p>You can close this tab and return to Telegram.</p>
          <span class="badge">STARFIRE AI OS</span>
        </div></body></html>""",
    )


@router.get("/status")
async def google_auth_status(telegram_id: str):
    """Check if a user has Google connected."""
    try:
        tid = int(telegram_id)
    except ValueError:
        return {"connected": False, "error": "invalid telegram_id"}
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == tid))
        user = result.scalar_one_or_none()
    if not user:
        return {"connected": False, "error": "user not found"}
    if not user.google_token_json:
        return {"connected": False}
    try:
        data = json.loads(user.google_token_json)
        return {
            "connected": True,
            "has_refresh_token": bool(data.get("refresh_token")),
            "scopes": data.get("scopes", []),
        }
    except Exception:
        return {"connected": False, "error": "malformed token"}


@router.get("/disconnect")
async def google_auth_disconnect(telegram_id: str):
    """Remove stored Google credentials for a user."""
    try:
        tid = int(telegram_id)
    except ValueError:
        return HTMLResponse("<h2>Invalid telegram_id.</h2>", status_code=400)
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == tid))
        user = result.scalar_one_or_none()
        if not user:
            return HTMLResponse("<h2>User not found.</h2>", status_code=404)
        user.google_token_json = None
        await session.commit()
    logger.info("google_oauth_disconnected", telegram_id=tid)
    return HTMLResponse(
        """<!DOCTYPE html><html><head><title>STARFIRE — Disconnected</title>
        <style>
          body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
               background:#000;color:#fff;display:flex;align-items:center;
               justify-content:center;min-height:100vh;margin:0;}
          .card{background:#111;border:1px solid #555;border-radius:12px;
                padding:40px;max-width:420px;text-align:center;}
          h2{color:#aaa;margin:0 0 12px;}p{color:#666;}
        </style></head><body>
        <div class="card">
          <h2>Google Disconnected</h2>
          <p>Your Google credentials have been removed from STARFIRE.</p>
          <p>Use /connect_google in Telegram to reconnect.</p>
        </div></body></html>"""
    )
