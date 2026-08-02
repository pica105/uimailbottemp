"""Yandex Mail sync via IMAP (aioimaplib) with XOAUTH2 authentication.

Tracks the last synced UID per account; fetches only newer messages.
Message bodies are parsed with the stdlib email module, then classified
with classifier.py heuristics.

IMAP response notes: ``uid("fetch", ...)`` returns one bytes element per
fetched message of the form::

    b"1 (UID 123 BODY[] {456}\\r\\n<raw rfc822 message>...)"

We strip the response prefix and trailing parenthesis before parsing.
"""

from __future__ import annotations

import email
import email.utils
import logging
import re
from datetime import datetime, timezone
from email.message import Message

import aiohttp
import aioimaplib

from .classifier import classify_yandex_message
from .config import settings
from .crypto import decrypt
from .database import Database

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.yandex.ru"
IMAP_PORT = 993
FETCH_BATCH = 50

# Matches the aioimaplib fetch response prefix: "1 (UID 123 BODY[] {456}\r\n"
_FETCH_PREFIX_RE = re.compile(rb"^\d+ \(UID \d+ BODY\[\] \{\d+\}\r?\n")


class YandexApiError(Exception):
    """Raised on Yandex API / IMAP failures."""


class YandexAuthError(YandexApiError):
    """Raised when XOAUTH2 authentication to the IMAP server fails.

    The caller (sync engine) reacts by refreshing the OAuth tokens and
    retrying once; if the refresh fails the account is deactivated.
    """


def yandex_oauth_redirect_uri() -> str:
    return f"{settings.BASE_URL.rstrip('/')}/oauth/yandex/callback"


async def exchange_code(code: str) -> dict:
    """Exchange a Yandex authorization code for tokens (used by oauth_server)."""
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.YANDEX_CLIENT_ID,
        "client_secret": settings.YANDEX_CLIENT_SECRET,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("https://oauth.yandex.ru/token", data=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise YandexApiError(
                    f"Yandex token exchange failed ({resp.status}): {data}"
                )
            return data


async def _connect(account: dict) -> aioimaplib.IMAP4_SSL:
    access_token = decrypt(account["encrypted_access_token"])
    email_address = account["email"]
    client = aioimaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    await client.wait_hello_from_server()
    # aioimaplib 2.x has a native xoauth2() (there is no generic
    # authenticate() anymore); it returns a Response, not raising on NO.
    resp = await client.xoauth2(email_address, access_token)
    if resp.result != "OK":
        await client.logout()
        detail = resp.lines[0] if resp.lines else b""
        raise YandexAuthError(
            f"XOAUTH2 auth failed for {email_address}: {detail!r}"
        )
    return client


def _extract_rfc822(line: bytes) -> bytes | None:
    """Strip the aioimaplib fetch prefix/trailing paren from a message line."""
    m = _FETCH_PREFIX_RE.match(line)
    if m:
        content = line[m.end():]
        if content.endswith(b")"):
            content = content[:-1]
        return content
    return None


async def _fetch_messages(client, start_uid: int) -> list[tuple[int, Message, bytes]]:
    """Fetch messages with UID >= start_uid. Returns (uid, parsed msg, raw)."""
    resp = await client.uid_search("ALL")
    if resp.result != "OK":
        raise YandexApiError(f"UID SEARCH failed: {resp.lines}")
    data = resp.lines
    if not data or not data[0]:
        return []
    uids = [int(u.decode()) for u in data[0].split() if u]
    pending = [u for u in uids if u >= start_uid][:FETCH_BATCH]
    if not pending:
        return []

    uid_set = ",".join(str(u) for u in pending)
    resp = await client.uid("fetch", uid_set, "(UID BODY.PEEK[])")
    if resp.result != "OK":
        raise YandexApiError(f"UID FETCH failed: {resp.lines}")
    raw = resp.lines

    results: list[tuple[int, Message, bytes]] = []
    # aioimaplib returns one line per message: b"<seq> (UID <uid> BODY[] {n}\r\n<msg>)"
    for line in raw:
        if not isinstance(line, bytes):
            continue
        content = _extract_rfc822(line)
        if content is None:
            continue
        # Parse the UID back out of the response line prefix.
        m = re.search(rb"\(UID (\d+)", line)
        if not m:
            continue
        uid = int(m.group(1))
        try:
            msg = email.message_from_bytes(content)
        except Exception:  # noqa: BLE001 - skip malformed message
            logger.warning("Skipping malformed IMAP message (uid %s)", uid)
            continue
        results.append((uid, msg, content))
    return results


def _message_to_record(uid: int, msg: Message) -> dict | None:
    subject = msg.get("Subject") or "(no subject)"
    sender = msg.get("From") or ""
    sender_name = None
    sender_email = sender.strip()
    if "<" in sender:
        sender_name = sender.split("<")[0].strip().strip('"') or None
        sender_email = sender.split("<")[1].split(">")[0].strip()

    date_str = msg.get("Date")
    received_at = int(datetime.now(timezone.utc).timestamp())
    if date_str:
        parsed = email.utils.parsedate_to_datetime(date_str)
        if parsed is not None:
            received_at = int(parsed.timestamp())

    # Plain-text body only (MVP per spec).
    body_text = ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain" and not part.get_filename():
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, "replace")
                    break
            except Exception:  # noqa: BLE001
                continue

    category = classify_yandex_message(msg)
    snippet = " ".join(body_text.split())[:200]

    return {
        "provider_message_id": f"yandex-{uid}",
        "sender_name": sender_name,
        "sender_email": sender_email,
        "subject": subject,
        "snippet": snippet,
        "body_text": body_text,
        "category": category,
        "received_at": received_at,
    }


async def sync_account(db: Database, account: dict) -> dict:
    """Sync a single Yandex account. Returns {'new': n, 'total': n}."""
    client = await _connect(account)
    try:
        await client.select("INBOX")
        start_uid = int(account.get("last_checkpoint") or 1)
        fetched = await _fetch_messages(client, start_uid)

        new_count = 0
        max_uid = start_uid
        for uid, msg, _raw in fetched:
            if uid > max_uid:
                max_uid = uid
            record = _message_to_record(uid, msg)
            if record is None:
                continue
            inserted = await db.upsert_message(account["id"], **record)
            new_count += 1 if inserted else 0

        await db.set_checkpoint(account["id"], str(max_uid))
        interval = account.get("polling_interval_seconds") or 300
        await db.schedule_next_sync(account["id"], interval)
        return {"new": new_count, "total": len(fetched)}
    finally:
        try:
            await client.logout()
        except Exception:  # noqa: BLE001
            pass
