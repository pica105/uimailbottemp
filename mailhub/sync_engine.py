"""Background mail synchronization engine.

Runs inside the same asyncio process. Every SYNC_BASE_INTERVAL_SECONDS (5s)
it looks for accounts whose next_sync_at has passed, syncs each provider,
and sends Telegram notifications for newly inserted messages. Each account
is scheduled with a fully automatic elastic interval (10s..5min). Failures
are isolated per account and backed off exponentially.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import aiohttp
from aiogram import Bot

from . import sync_gmail
from . import sync_yandex
from .bot_handlers import i18n, send_new_mail_notification
from .config import settings
from .crypto import decrypt, encrypt
from .database import Database, SUPPRESSED_NOTIFICATION_CATEGORIES

logger = logging.getLogger(__name__)


async def _sync_one_account(db: Database, account: dict, session: aiohttp.ClientSession) -> dict:
    provider = account["provider"]
    if provider == "gmail":
        return await sync_gmail.sync_account(db, account, session)
    if provider == "yandex":
        return await sync_yandex.sync_account(db, account)
    raise ValueError(f"Unknown provider: {provider}")


async def _refresh_tokens(db: Database, account: dict) -> dict | None:
    """Try to refresh an account's tokens. Returns updated account or None."""
    try:
        if account["provider"] == "gmail":
            return await sync_gmail.refresh_and_update_account(db, account)
        if account["provider"] == "yandex":
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": decrypt(account.get("encrypted_refresh_token") or ""),
                "client_id": settings.YANDEX_CLIENT_ID,
                "client_secret": settings.YANDEX_CLIENT_SECRET,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post("https://oauth.yandex.ru/token", data=payload) as resp:
                    data = await resp.json()
                    if resp.status != 200:
                        return None
            access = encrypt(data["access_token"])
            expires_at = int(time.time()) + int(data.get("expires_in", 3600))
            await db.update_account_tokens(
                account["id"], access, account.get("encrypted_refresh_token"), expires_at
            )
            return await db.get_account(account["id"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Token refresh failed for account %s: %s", account.get("id"), exc)
    return None


async def _deactivate_and_notify(db: Database, bot: Bot, account: dict) -> None:
    """Deactivate an account and tell its owner why (spec §7.2)."""
    await db.set_account_active(account["id"], False)
    logger.warning("Account %s deactivated (token refresh failed)", account["email"])
    lang = account.get("user_language") or "en"
    text = i18n.t(lang, "account_deactivated", email=account["email"])
    try:
        await bot.send_message(account["user_telegram_id"], text)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to notify deactivation for %s", account["email"])


async def _sync_account_with_retry(
    db: Database,
    bot: Bot,
    account: dict,
    session: aiohttp.ClientSession,
    *,
    retried: bool = False,
) -> bool:
    """Sync one account; on auth failure refresh tokens and retry once.

    ``retried`` guards against infinite refresh-retry loops when a fresh
    token is still rejected (e.g. IMAP disabled server-side). Returns True
    on success so the caller can schedule the next (elastic) check.
    """
    try:
        result = await _sync_one_account(db, account, session)
        if result.get("new", 0) > 0:
            logger.info(
                "Synced %s (%s): %d new of %d",
                account["provider"], account["email"], result["new"], result["total"],
            )
        return True
    except sync_gmail.GmailApiError as exc:
        if "unauthorized" in str(exc) and not retried:
            updated = await _refresh_tokens(db, account)
            if updated is None:
                await _deactivate_and_notify(db, bot, account)
            else:
                # Retry once with the fresh token, keeping the joined user
                # fields (language, interval, muted categories) intact.
                updated = {**account, **updated}
                return await _sync_account_with_retry(
                    db, bot, updated, session, retried=True
                )
            return False
        await db.increment_error(account["id"])
        logger.error("Sync failed for %s: %s", account["email"], exc)
        return False
    except sync_yandex.YandexAuthError as exc:
        # Yandex rejects the access token (e.g. issued before IMAP access
        # was enabled). Refresh once and retry; deactivate on failure.
        if not retried:
            logger.warning(
                "Yandex auth failed for %s, refreshing tokens: %s",
                account["email"], exc,
            )
            updated = await _refresh_tokens(db, account)
            if updated is None:
                await _deactivate_and_notify(db, bot, account)
            else:
                updated = {**account, **updated}
                return await _sync_account_with_retry(
                    db, bot, updated, session, retried=True
                )
            return False
        await db.increment_error(account["id"])
        logger.error("Sync failed for %s: %s", account["email"], exc)
        return False
    except Exception as exc:  # noqa: BLE001 - per-account isolation
        await db.increment_error(account["id"])
        logger.error("Sync failed for %s: %s", account["email"], exc)
        return False


async def _adaptive_interval(db: Database, account: dict) -> int:
    """Elastic per-account polling interval (fully automatic).

    - fresh mail (newest message < 200s old) → POLL_MIN (10s)
    - grows proportionally with idle time:   gap // 10
    - capped at POLL_MAX (5 min)
    - a new message resets it back to POLL_MIN automatically, because the
      gap collapses to ~0

    When no mail has ever been imported the maximum (5 min) is used.
    The interval is NOT user-configurable by design.
    """
    cap = settings.POLL_MAX_SECONDS
    last_at = await db.get_last_message_at(account["id"])
    if last_at is None:
        return cap
    gap = max(0, int(time.time()) - int(last_at))
    return max(settings.POLL_MIN_SECONDS, min(cap, gap // 10))


async def _notify_new_messages(
    db: Database, bot: Bot, account: dict, *, skip_initial: bool = False
) -> None:
    """Send notifications for un-notified messages of this account.

    ``skip_initial=True`` suppresses notifications for the very first import
    (the account's cache was empty before this sync) — the user just
    connected the account and should not be flooded with old mail.
    """
    muted: list[str] = []
    try:
        muted = json.loads(account.get("user_muted_categories") or "[]")
    except json.JSONDecodeError:
        muted = []

    if skip_initial:
        # First import: cache all the mail but do not notify about it.
        await db.mark_all_notified(account["id"])
        return

    messages = await db.get_unnotified_messages(account["id"], limit=10)
    lang = account.get("user_language") or "en"

    for msg in messages:
        if msg["category"] in SUPPRESSED_NOTIFICATION_CATEGORIES or msg["category"] in muted:
            # Mark muted messages as notified so they're not re-sent later.
            await db.mark_notified(msg["id"])
            continue
        await send_new_mail_notification(
            bot, db, account["user_telegram_id"], lang, msg
        )


async def sync_loop(db: Database, bot: Bot, stop_event: asyncio.Event) -> None:
    """Main loop: runs forever until stop_event is set."""
    logger.info("Sync engine started (base interval %ss)", settings.SYNC_BASE_INTERVAL_SECONDS)
    session = aiohttp.ClientSession()
    try:
        while not stop_event.is_set():
            try:
                accounts = await db.get_active_accounts()
                now = int(time.time())
                for account in accounts:
                    next_sync = account.get("next_sync_at")
                    if next_sync is None or int(next_sync) <= now:
                        was_empty = await db.get_message_count(account["id"]) == 0
                        ok = await _sync_account_with_retry(db, bot, account, session)
                        await _notify_new_messages(
                            db, bot, account, skip_initial=was_empty
                        )
                        if ok:
                            # The engine owns scheduling: poll fast while
                            # mail is fresh, back off while it is idle.
                            interval = await _adaptive_interval(db, account)
                            await db.schedule_next_sync(account["id"], interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - engine must keep running
                logger.exception("Sync engine iteration failed: %s", exc)
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.SYNC_BASE_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass
    finally:
        await session.close()
        logger.info("Sync engine stopped")
