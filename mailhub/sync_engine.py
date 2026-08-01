"""Background mail synchronization engine.

Runs inside the same asyncio process. Every ~60 seconds it looks for
accounts whose next_sync_at has passed, syncs each provider, and sends
Telegram notifications for newly inserted messages. Failures are isolated
per account and backed off exponentially.
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
from .database import Database

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
    db: Database, bot: Bot, account: dict, session: aiohttp.ClientSession
) -> None:
    try:
        result = await _sync_one_account(db, account, session)
        if result.get("new", 0) > 0:
            logger.info(
                "Synced %s (%s): %d new of %d",
                account["provider"], account["email"], result["new"], result["total"],
            )
    except sync_gmail.GmailApiError as exc:
        if "unauthorized" in str(exc):
            updated = await _refresh_tokens(db, account)
            if updated is None:
                await _deactivate_and_notify(db, bot, account)
            else:
                # Retry once with the fresh token, keeping the joined user
                # fields (language, interval, muted categories) intact.
                updated = {**account, **updated}
                await _sync_account_with_retry(db, bot, updated, session)
            return
        await db.increment_error(account["id"])
        logger.error("Sync failed for %s: %s", account["email"], exc)
    except Exception as exc:  # noqa: BLE001 - per-account isolation
        await db.increment_error(account["id"])
        logger.error("Sync failed for %s: %s", account["email"], exc)


async def _notify_new_messages(db: Database, bot: Bot, account: dict) -> None:
    """Send notifications for un-notified messages of this account."""
    muted: list[str] = []
    try:
        muted = json.loads(account.get("user_muted_categories") or "[]")
    except json.JSONDecodeError:
        muted = []

    messages = await db.get_unnotified_messages(account["id"], limit=10)
    lang = account.get("user_language") or "en"

    for msg in messages:
        if msg["category"] in muted:
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
                        await _sync_account_with_retry(db, bot, account, session)
                        await _notify_new_messages(db, bot, account)
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
