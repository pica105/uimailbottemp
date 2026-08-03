"""Yandex Mail sync via IMAP (aioimaplib) with XOAUTH2 authentication.

Tracks the last synced UID per account; fetches only newer messages.
Message bodies are parsed with the stdlib email module, then classified
with classifier.py heuristics.

IMAP response notes (aioimaplib 2.0.1): ``uid("fetch", ...)`` returns the
response *split* into several elements per fetched message::

    b"1 FETCH (UID 123 BODY[] {456}"   <- header line (bytes)
    bytearray(b"<raw rfc822 message>") <- literal body (bytearray)
    b")"                                <- closing paren

We walk the response lines, pairing each ``FETCH (UID ...`` header with the
literal that follows it.
"""

from __future__ import annotations

import email
import email.utils
import logging
import re
from contextlib import suppress
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from html.parser import HTMLParser

import aiohttp
import aioimaplib

from .classifier import classify_yandex_message
from .config import settings
from .crypto import decrypt
from .database import Database

logger = logging.getLogger(__name__)


class _HtmlTextExtractor(HTMLParser):
    """Collect visible text from an HTML part (skips script/style)."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
        if tag in ("p", "br", "div", "tr", "li", "h1", "h2", "h3", "blockquote"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    """Best-effort HTML → plain text conversion (stdlib only)."""
    parser = _HtmlTextExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - malformed HTML must not break sync
        return ""
    text = " ".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _decode_header_value(value: str | None) -> str:
    """Decode RFC 2047 encoded-words ("=?utf-8?b?...?=") into plain text."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001 - fall back to the raw value
        return value

IMAP_HOST = "imap.yandex.ru"
IMAP_PORT = 993
FETCH_BATCH = 50

# Matches the aioimaplib 2.x fetch response header:
#   b"1 FETCH (UID 123 BODY[] {456}"
_FETCH_UID_RE = re.compile(rb"\bUID\s+(\d+)\b")
_FETCH_FLAGS_RE = re.compile(rb"\bFLAGS\s+\(([^)]*)\)")


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
        with suppress(Exception):  # noqa: BLE001 - logout must not mask the real error
            await client.logout()
        detail = resp.lines[0] if resp.lines else b""
        raise YandexAuthError(
            f"XOAUTH2 auth failed for {email_address}: {detail!r}"
        )
    return client


async def _fetch_messages(
    client, start_uid: int, criteria: str = "ALL"
) -> list[tuple[int, Message, bytes, bool]]:
    """Fetch messages with UID >= start_uid, including provider read state."""
    resp = await client.uid_search(criteria)
    if resp.result != "OK":
        raise YandexApiError(f"UID SEARCH failed: {resp.lines}")
    data = resp.lines
    if not data or not data[0]:
        return []
    uids = [int(u) for u in data[0].split() if u.isdigit()]
    # Newest messages first (like the Gmail first sync), so the initial
    # import contains recent mail rather than the oldest batch.
    pending = [u for u in uids if u >= start_uid][-FETCH_BATCH:]
    if not pending:
        return []

    uid_set = ",".join(str(u) for u in pending)
    resp = await client.uid("fetch", uid_set, "(UID FLAGS BODY.PEEK[])")
    if resp.result != "OK":
        raise YandexApiError(f"UID FETCH failed: {resp.lines}")
    raw = resp.lines

    results: list[tuple[int, Message, bytes, bool]] = []
    # Walk the split response: each message is a header line followed by the
    # literal (bytearray) body and a closing paren line.
    i = 0
    while i < len(raw):
        line = raw[i]
        i += 1
        if not isinstance(line, bytes):
            continue
        if b"BODY[" not in line and b"BODY.PEEK[" not in line:
            continue
        m = _FETCH_UID_RE.search(line)
        if m is None:
            continue
        uid = int(m.group(1))
        flags_match = _FETCH_FLAGS_RE.search(line)
        flags = flags_match.group(1) if flags_match else b""
        is_read = b"\\Seen" in flags
        if i >= len(raw) or not isinstance(raw[i], (bytes, bytearray)):
            logger.warning("Skipping IMAP message (uid %s): missing literal", uid)
            continue
        content = bytes(raw[i])
        i += 1
        try:
            msg = email.message_from_bytes(content)
        except Exception:  # noqa: BLE001 - skip malformed message
            logger.warning("Skipping malformed IMAP message (uid %s)", uid)
            continue
        results.append((uid, msg, content, is_read))
    return results


def _message_to_record(uid: int, msg: Message) -> dict | None:
    subject = _decode_header_value(msg.get("Subject")) or "(no subject)"
    sender = msg.get("From") or ""
    sender_name = None
    sender_email = sender.strip()
    if "<" in sender:
        name_part = sender.split("<")[0].strip().strip('"')
        sender_name = _decode_header_value(name_part) or None
        sender_email = sender.split("<")[1].split(">")[0].strip()

    date_str = msg.get("Date")
    received_at = int(datetime.now(timezone.utc).timestamp())
    if date_str:
        parsed = email.utils.parsedate_to_datetime(date_str)
        if parsed is not None:
            received_at = int(parsed.timestamp())

    # Prefer the text/plain part; fall back to stripping HTML (most
    # commercial mail is HTML-only and would otherwise have no body).
    body_text = ""
    for part in msg.walk():
        if part.get_filename():
            continue
        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True)
        except Exception:  # noqa: BLE001
            continue
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, "replace")
        except Exception:  # noqa: BLE001 - unknown charset
            text = payload.decode("utf-8", "replace")
        if content_type == "text/plain":
            body_text = text
            break
        if not body_text:
            body_text = _html_to_text(text)

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


async def mark_message_read(account: dict, provider_message_id: str) -> None:
    """Set the \\Seen flag on a Yandex message via IMAP STORE."""
    if not provider_message_id.startswith("yandex-"):
        raise YandexApiError(f"Unexpected yandex message id: {provider_message_id!r}")
    uid = provider_message_id.split("-", 1)[1]
    client = await _connect(account)
    try:
        await client.select("INBOX")
        resp = await client.uid("store", uid, "+FLAGS", r"(\Seen)")
        if resp.result != "OK":
            raise YandexApiError(f"STORE \\Seen failed for uid {uid}: {resp.lines}")
    finally:
        try:
            await client.logout()
        except Exception:  # noqa: BLE001
            pass


async def sync_account(db: Database, account: dict) -> dict:
    """Sync a single Yandex account. Returns {'new': n, 'total': n}."""
    client = await _connect(account)
    try:
        await client.select("INBOX")
        start_uid = int(account.get("last_checkpoint") or 1)
        bootstrap = not bool(account.get("unread_bootstrap_done"))
        fetched = await _fetch_messages(client, start_uid, "ALL")
        if bootstrap:
            # Existing accounts may have a stale checkpoint and only a few
            # cached messages. Always backfill the newest unseen UIDs once.
            unread = await _fetch_messages(client, 1, "UNSEEN")
            by_uid = {item[0]: item for item in fetched}
            by_uid.update({item[0]: item for item in unread})
            fetched = list(by_uid.values())

        new_count = 0
        max_uid = start_uid
        for uid, msg, _raw, is_read in fetched:
            if uid > max_uid:
                max_uid = uid
            record = _message_to_record(uid, msg)
            if record is None:
                continue
            record["is_read"] = is_read
            inserted = await db.upsert_message(account["id"], **record)
            if not inserted:
                cached = await db._fetchone(
                    "SELECT id FROM messages_cache WHERE account_id = ? AND provider_message_id = ?",
                    (account["id"], record["provider_message_id"]),
                )
                if cached:
                    await db.update_message_from_provider(cached["id"], **record)
            new_count += 1 if inserted else 0

        await db.set_checkpoint(account["id"], str(max_uid))
        if bootstrap:
            await db.mark_unread_bootstrap_done(account["id"])
        return {"new": new_count, "total": len(fetched)}
    finally:
        try:
            await client.logout()
        except Exception:  # noqa: BLE001
            pass
