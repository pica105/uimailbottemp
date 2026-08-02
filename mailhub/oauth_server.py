"""aiohttp web server: OAuth callbacks + Mini App REST API.

- GET /oauth/{provider}/callback — OAuth redirect target (browser flow)
- GET /api/health            — liveness probe
- GET  /api/accounts         — list accounts for the authenticated user
- DELETE /api/accounts/{id}  — unlink account
- GET  /api/accounts/{id}/messages?category=&limit=&offset=
- GET  /api/messages/{id}    — single message
- POST /api/messages/{id}/read
- GET  /api/settings
- PATCH /api/settings

Every /api/* route validates the Telegram WebApp initData (HMAC-SHA256).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from html import escape
from urllib.parse import parse_qs

from aiohttp import web

from .bot_handlers import i18n
from .config import settings
from .crypto import encrypt
from .database import Database
from . import sync_gmail
from . import sync_yandex
from .mark_read import spawn_mark_read

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# initData validation
# ---------------------------------------------------------------------------
def _parse_init_data(init_data: str) -> dict[str, str]:
    """Parse initData query string into a dict."""
    result: dict[str, str] = {}
    for key, values in parse_qs(init_data, keep_blank_values=True).items():
        result[key] = values[0]
    return result


def _compute_secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def validate_init_data(init_data: str, max_age_seconds: int = 86400) -> dict[str, str] | None:
    """Validate Telegram WebApp initData; return parsed fields or None.

    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        return None
    parsed = _parse_init_data(init_data)
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items()) if k != "hash"
    )
    secret_key = _compute_secret_key(settings.BOT_TOKEN)
    computed = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None

    auth_date_str = parsed.get("auth_date", "0") or "0"
    try:
        auth_date = int(auth_date_str)
    except (TypeError, ValueError):
        return None
    if time.time() - auth_date > max_age_seconds:
        return None
    return parsed


def _init_data_middleware(db: Database):
    """Reject /api/* requests without valid initData."""

    @web.middleware
    async def middleware(request: web.Request, handler):
        path = request.path
        if not path.startswith("/api/"):
            return await handler(request)
        if path == "/api/health":
            return await handler(request)
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        data = validate_init_data(init_data)
        if data is None:
            return web.json_response(
                {"error": "unauthorized", "message": "Invalid or expired initData"}, status=401
            )
        request["init_data"] = data
        request["telegram_id"] = _user_id(data)
        return await handler(request)

    return middleware


def _user_id(data: dict[str, str]) -> int:
    """Extract telegram user id from the JSON 'user' field of initData."""
    try:
        user = json.loads(data.get("user", "{}"))
        return int(user.get("id", 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0


def _public_account(acc: dict) -> dict:
    return {
        "id": acc["id"],
        "provider": acc["provider"],
        "email": acc["email"],
        "is_active": bool(acc["is_active"]),
        "sync_error_count": acc["sync_error_count"],
    }


def _public_message(msg: dict) -> dict:
    return {
        "id": msg["id"],
        "account_id": msg["account_id"],
        "sender_name": msg["sender_name"],
        "sender_email": msg["sender_email"],
        "subject": msg["subject"],
        "snippet": msg["snippet"],
        "body_text": msg["body_text"],
        "category": msg["category"],
        "received_at": msg["received_at"],
        "is_read": bool(msg["is_read"]),
    }


# ---------------------------------------------------------------------------
# OAuth callbacks
# ---------------------------------------------------------------------------
async def _handle_oauth_callback(request: web.Request) -> web.Response:
    provider = request.match_info["provider"]
    code = request.query.get("code", "")
    state = request.query.get("state", "")
    error = request.query.get("error", "")
    db: Database = request.app["db"]

    # Determine the user's language for localized messages.
    state_row = await db.get_oauth_state(state) if state else None
    user = await db.get_user(state_row["user_id"]) if state_row else None
    lang = (user or {}).get("language", "en")

    if error or not code or not state:
        return web.Response(
            text=i18n.t(lang, "oauth_failed", error=error or "missing code/state"),
            content_type="text/html",
        )

    if state_row is None or state_row["provider"] != provider:
        return web.Response(
            text=i18n.t(lang, "oauth_invalid_state"), content_type="text/html"
        )

    try:
        if provider == "gmail":
            tokens = await sync_gmail.exchange_code(code)
            email_address = await sync_gmail.fetch_profile(tokens["access_token"])
        elif provider == "yandex":
            tokens = await sync_yandex.exchange_code(code)
            # Yandex returns the user email only via /info endpoint.
            email_address = await _yandex_email(tokens["access_token"])
        else:
            raise ValueError(f"Unknown provider: {provider}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("OAuth exchange failed for %s", provider)
        return web.Response(
            text=i18n.t(lang, "oauth_failed", error=str(exc)), content_type="text/html"
        )

    refresh_token = tokens.get("refresh_token")
    access_token = tokens["access_token"]
    expires_at = int(time.time()) + int(tokens.get("expires_in", 3600))

    user_id = state_row["user_id"]
    existing = await db.get_accounts(user_id)
    already = next((a for a in existing if a["email"].lower() == email_address.lower()), None)

    if already:
        # Update tokens for the existing account instead of failing.
        await db.update_account_tokens(
            already["id"], encrypt(access_token), encrypt(refresh_token or ""), expires_at
        )
        await db.set_account_active(already["id"], True)
        # Resume syncing immediately after re-authorization (clears backoff).
        await db.schedule_next_sync(already["id"], 0)
        text = i18n.t(lang, "account_already_connected", email=email_address)
    else:
        await db.add_account(
            user_id,
            provider,
            email_address,
            encrypt(access_token),
            encrypt(refresh_token or ""),
            expires_at,
        )
        text = i18n.t(lang, "account_connected", email=email_address)

    await db.delete_oauth_state(state)

    # Notify the user in Telegram.
    bot = request.app.get("bot")
    if bot is not None:
        try:
            await bot.send_message(user_id, text)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to notify user %s about connected account", user_id)

    html = (
        "<html><body style='font-family:system-ui;display:flex;align-items:center;"
        "justify-content:center;height:100vh;margin:0;background:#FFF7ED'>"
        "<div style='text-align:center'><h1 style='color:#D97706'>✅</h1>"
        f"<p style='color:#444'>{escape(text)}</p>"
        "<p style='color:#999'>You can close this tab and return to Telegram.</p>"
        "</div></body></html>"
    )
    return web.Response(text=html, content_type="text/html")


async def _yandex_email(access_token: str) -> str:
    """Fetch the Yandex account login/email via the /info endpoint."""
    from aiohttp import ClientSession

    async with ClientSession() as session:
        async with session.get(
            "https://login.yandex.ru/info",
            headers={"Authorization": f"OAuth {access_token}"},
        ) as resp:
            data = await resp.json()
    email = data.get("default_email") or data.get("login") or ""
    if not email:
        raise ValueError("Could not determine Yandex email")
    return email


# ---------------------------------------------------------------------------
# API handlers
# ---------------------------------------------------------------------------
async def _get_telegram_id(request: web.Request) -> int:
    return _user_id(request["init_data"])


async def api_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def api_accounts(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    telegram_id = await _get_telegram_id(request)
    if telegram_id <= 0:
        return web.json_response({"error": "unauthorized"}, status=401)
    accounts = await db.get_accounts(telegram_id)
    return web.json_response({"accounts": [_public_account(a) for a in accounts]})


async def _parse_id(request: web.Request, name: str = "id") -> int | None:
    """Parse a path id; return None for non-numeric input (→ 404)."""
    try:
        return int(request.match_info[name])
    except (KeyError, TypeError, ValueError):
        return None


async def api_delete_account(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    telegram_id = await _get_telegram_id(request)
    account_id = await _parse_id(request)
    if account_id is None:
        return web.json_response({"error": "not_found"}, status=404)
    account = await db.get_account(account_id)
    if account is None or account["user_id"] != telegram_id:
        return web.json_response({"error": "not_found"}, status=404)
    await db.delete_account(account_id)
    return web.json_response({"ok": True})


async def api_account_messages(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    telegram_id = await _get_telegram_id(request)
    account_id = await _parse_id(request)
    if account_id is None:
        return web.json_response({"error": "not_found"}, status=404)
    account = await db.get_account(account_id)
    if account is None or account["user_id"] != telegram_id:
        return web.json_response({"error": "not_found"}, status=404)

    category = request.query.get("category") or None
    try:
        limit = max(1, min(int(request.query.get("limit", "50")), 100))
        offset = max(0, int(request.query.get("offset", "0")))
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid_pagination"}, status=400)
    messages = await db.get_messages(account_id, category=category, limit=limit, offset=offset)
    return web.json_response({"messages": [_public_message(m) for m in messages]})


async def api_message(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    telegram_id = await _get_telegram_id(request)
    message_id = await _parse_id(request)
    if message_id is None:
        return web.json_response({"error": "not_found"}, status=404)
    msg = await db.get_message(message_id)
    if msg is None:
        return web.json_response({"error": "not_found"}, status=404)
    account = await db.get_account(msg["account_id"])
    if account is None or account["user_id"] != telegram_id:
        return web.json_response({"error": "not_found"}, status=404)
    return web.json_response({"message": _public_message(msg)})


async def api_mark_read(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    telegram_id = await _get_telegram_id(request)
    message_id = await _parse_id(request)
    if message_id is None:
        return web.json_response({"error": "not_found"}, status=404)
    msg = await db.get_message(message_id)
    if msg is None:
        return web.json_response({"error": "not_found"}, status=404)
    account = await db.get_account(msg["account_id"])
    if account is None or account["user_id"] != telegram_id:
        return web.json_response({"error": "not_found"}, status=404)
    await db.mark_read(message_id)
    # Push the read state to the real mailbox in the background; the API
    # responds instantly even if the provider call takes a second.
    spawn_mark_read(db, msg["account_id"], msg["provider_message_id"])
    return web.json_response({"ok": True})


async def api_get_settings(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    telegram_id = await _get_telegram_id(request)
    settings_row = await db.get_settings(telegram_id)
    settings_row["accounts"] = [
        _public_account(a) for a in await db.get_accounts(telegram_id)
    ]
    return web.json_response({"settings": settings_row})


async def api_update_settings(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    telegram_id = await _get_telegram_id(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)

    language = body.get("language")
    if language is not None and language not in ("ru", "en"):
        return web.json_response({"error": "invalid_language"}, status=400)

    polling_interval: int | None = None
    if body.get("polling_interval_seconds") is not None:
        try:
            polling_interval = int(body["polling_interval_seconds"])
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_interval"}, status=400)
        if not (
            settings.POLL_MIN_SECONDS
            <= polling_interval
            <= settings.SETTINGS_MAX_INTERVAL_SECONDS
        ):
            return web.json_response({"error": "invalid_interval"}, status=400)

    muted = body.get("muted_categories")
    if muted is not None and not isinstance(muted, list):
        return web.json_response({"error": "invalid_muted"}, status=400)
    if muted is not None:
        valid = {"promo", "spam", "other"}
        if any(c not in valid for c in muted):
            return web.json_response({"error": "invalid_muted"}, status=400)

    updated = await db.update_settings(
        telegram_id,
        language=language,
        polling_interval_seconds=polling_interval,
        muted_categories=muted,
    )
    # Keep the response shape identical to GET /api/settings so the Mini App
    # can validate it with a single schema.
    updated["accounts"] = [_public_account(a) for a in await db.get_accounts(telegram_id)]
    return web.json_response({"settings": updated})


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app(db: Database, bot=None) -> web.Application:
    app = web.Application(middlewares=[_init_data_middleware(db)])
    app["db"] = db
    app["bot"] = bot

    app.router.add_get("/api/health", api_health)
    app.router.add_get("/oauth/{provider}/callback", _handle_oauth_callback)

    app.router.add_get("/api/accounts", api_accounts)
    app.router.add_delete("/api/accounts/{id}", api_delete_account)
    app.router.add_get("/api/accounts/{id}/messages", api_account_messages)
    app.router.add_get("/api/messages/{id}", api_message)
    app.router.add_post("/api/messages/{id}/read", api_mark_read)
    app.router.add_get("/api/settings", api_get_settings)
    app.router.add_patch("/api/settings", api_update_settings)
    return app
