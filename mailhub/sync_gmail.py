"""Gmail incremental sync implemented with plain REST calls over aiohttp.

We deliberately avoid google-api-python-client: it is a blocking SDK, and
the spec forbids blocking calls inside the single asyncio process. The
Gmail API is plain JSON over HTTPS, so aiohttp gives us the same
functionality with zero blocking and fewer dependencies.

Token exchange / refresh use the standard Google OAuth2 token endpoint.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp

from .config import settings
from .crypto import decrypt, encrypt
from .database import Database

logger = logging.getLogger(__name__)

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"

GMAIL_CATEGORY_MAP = {
    "CATEGORY_PERSONAL": "important",
    "CATEGORY_PROMOTIONS": "promo",
    "CATEGORY_SOCIAL": "promo",
    "CATEGORY_UPDATES": "other",
    "CATEGORY_FORUMS": "other",
}


class GmailApiError(Exception):
    """Raised when the Gmail API returns an unexpected status."""


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def gmail_oauth_redirect_uri() -> str:
    return f"{settings.BASE_URL.rstrip('/')}/oauth/gmail/callback"


async def exchange_code(code: str) -> dict:
    """Exchange an authorization code for tokens (used by oauth_server)."""
    payload = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": gmail_oauth_redirect_uri(),
        "grant_type": "authorization_code",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(TOKEN_URL, data=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise GmailApiError(
                    f"Token exchange failed ({resp.status}): {data.get('error_description', data)}"
                )
            return data


async def refresh_access_token(refresh_token: str) -> dict:
    payload = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(TOKEN_URL, data=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise GmailApiError(
                    f"Token refresh failed ({resp.status}): {data.get('error_description', data)}"
                )
            return data


async def _get(
    session: aiohttp.ClientSession,
    access_token: str,
    url: str,
    params: dict | None = None,
) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with session.get(url, params=params, headers=headers) as resp:
        if resp.status == 401:
            raise GmailApiError("unauthorized")
        if resp.status != 200:
            body = await resp.text()
            raise GmailApiError(f"GET {url} -> {resp.status}: {body[:300]}")
        return await resp.json()


async def fetch_profile(access_token: str) -> str:
    async with aiohttp.ClientSession() as session:
        data = await _get(session, access_token, f"{GMAIL_API}/profile")
        return data["emailAddress"]


def _parse_internal_date(internal_date: str | None, message: dict) -> int:
    """Gmail internalDate is ms epoch; fall back to message metadata."""
    if internal_date:
        try:
            return int(internal_date) // 1000
        except (TypeError, ValueError):
            pass
    return _now_ts()


async def list_messages(
    access_token: str, history_id: str | None = None, max_results: int = 50
) -> tuple[list[dict], str]:
    """Return (messages, new_history_id).

    First sync: fetch the latest ``max_results`` messages.
    Incremental: use users.history.list from ``history_id``.
    """
    async with aiohttp.ClientSession() as session:
        if history_id:
            data = await _get(
                session,
                access_token,
                f"{GMAIL_API}/history",
                {
                    "startHistoryId": history_id,
                    "maxResults": str(settings.GMAIL_HISTORY_PAGE_SIZE),
                    "labelId": "INBOX",
                    "historyTypes": "messageAdded",
                },
            )
            history = data.get("history", [])
            new_history_id = data.get("historyId") or history_id
            messages: list[dict] = []
            for item in history:
                for msg in item.get("messagesAdded", []):
                    messages.append(msg["message"])
            # history may return duplicates across pages; dedupe by id.
            seen: set[str] = set()
            unique: list[dict] = []
            for m in messages:
                if m["id"] not in seen:
                    seen.add(m["id"])
                    unique.append(m)
            return unique[:max_results], new_history_id

        # First sync: latest messages from INBOX. messages.list does not
        # return historyId — it comes from users.getProfile instead.
        data = await _get(
            session,
            access_token,
            f"{GMAIL_API}/messages",
            {"labelIds": "INBOX", "maxResults": str(max_results)},
        )
        messages = data.get("messages", [])
        profile = await _get(session, access_token, f"{GMAIL_API}/profile")
        return messages, profile.get("historyId", "")


async def fetch_message_full(access_token: str, message_id: str) -> dict:
    async with aiohttp.ClientSession() as session:
        return await _get(
            session,
            access_token,
            f"{GMAIL_API}/messages/{message_id}",
            {"format": "full"},
        )


def _extract_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_body(payload: dict) -> str:
    """Best-effort extraction of a plain-text body from a Gmail payload."""
    import base64

    def _walk(node: dict) -> str:
        mime = node.get("mimeType", "")
        if mime == "text/plain" and node.get("body", {}).get("data"):
            raw = node["body"]["data"]
            try:
                return base64.urlsafe_b64decode(raw.encode()).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                return ""
        for part in node.get("parts", []):
            text = _walk(part)
            if text:
                return text
        return ""

    return _walk(payload)


def message_to_record(message: dict) -> dict:
    """Convert a Gmail message resource into a messages_cache row dict."""
    payload = message.get("payload", {})
    headers = payload.get("headers", [])
    internal_date = message.get("internalDate")
    received_at = _parse_internal_date(internal_date, message)
    sender = _extract_header(headers, "From")
    sender_name, sender_email = _split_sender(sender)

    labels = message.get("labelIds", [])
    category = "important"
    for label in labels:
        if label in GMAIL_CATEGORY_MAP:
            category = GMAIL_CATEGORY_MAP[label]
            break

    return {
        "provider_message_id": message["id"],
        "sender_name": sender_name,
        "sender_email": sender_email,
        "subject": _extract_header(headers, "Subject") or "(no subject)",
        "snippet": message.get("snippet", ""),
        "body_text": _decode_body(payload),
        "category": category,
        "received_at": received_at,
    }


def _split_sender(from_header: str) -> tuple[str | None, str | None]:
    """'Name <a@b.c>' -> ('Name', 'a@b.c'). Handles bare addresses."""
    if not from_header:
        return None, None
    if "<" in from_header:
        name = from_header.split("<")[0].strip().strip('"')
        email = from_header.split("<")[1].split(">")[0].strip()
        return (name or None), email or None
    return None, from_header.strip()


async def sync_account(
    db: Database, account: dict, session: aiohttp.ClientSession | None = None
) -> dict:
    """Sync a single Gmail account. Returns a dict with counts for logging.

    Raises GmailApiError("unauthorized") when the access token is invalid,
    in which case the caller (sync_engine) attempts one token refresh.
    """
    access_token = decrypt(account["encrypted_access_token"])
    refresh_token = decrypt(account["encrypted_refresh_token"])

    own_session = session is None
    session = session or aiohttp.ClientSession()
    try:
        messages, new_history_id = await list_messages(
            access_token, account["last_checkpoint"] or None, max_results=50
        )
        new_count = 0
        for msg in messages:
            full = await fetch_message_full(access_token, msg["id"])
            record = message_to_record(full)
            inserted = await db.upsert_message(account["id"], **record)
            new_count += 1 if inserted else 0

        if new_history_id:
            await db.set_checkpoint(account["id"], new_history_id)
        await db.schedule_next_sync(
            account["id"], account.get("polling_interval_seconds") or 300
        )
        return {"new": new_count, "total": len(messages)}
    finally:
        if own_session:
            await session.close()


async def refresh_and_update_account(db: Database, account: dict) -> dict | None:
    """Refresh tokens for an account; returns updated account dict or None."""
    refresh_token = decrypt(account["encrypted_refresh_token"])
    if not refresh_token:
        return None
    data = await refresh_access_token(refresh_token)
    access = data["access_token"]
    expires_at = _now_ts() + int(data.get("expires_in", 3600))
    await db.update_account_tokens(
        account["id"], encrypt(access), encrypt(refresh_token), expires_at
    )
    return await db.get_account(account["id"])
