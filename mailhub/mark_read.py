"""Propagate "mark as read" to the real mailbox (Gmail / Yandex).

The Mini App and the bot only ever set the local ``is_read`` flag; this
module pushes the same state to the provider so the change is visible in
the actual mailbox too. The call is best-effort: failures (e.g. a Gmail
token that still has the old ``readonly`` scope) are logged and never
break the local response.

Lives in its own module to avoid the import cycle between ``sync_engine``
(which imports ``bot_handlers``) and ``bot_handlers`` / ``oauth_server``.
"""

from __future__ import annotations

import asyncio
import logging

from . import sync_gmail
from . import sync_yandex
from .database import Database

logger = logging.getLogger(__name__)

# Keep strong references to background tasks so they are not garbage
# collected (and cancelled) before finishing.
_background_tasks: set[asyncio.Task] = set()


async def mark_read_on_provider(
    db: Database, account_id: int, provider_message_id: str
) -> None:
    """Best-effort: set the \\Seen / remove UNREAD in the real mailbox."""
    account = await db.get_account(account_id)
    if account is None:
        return
    try:
        if account["provider"] == "gmail":
            await sync_gmail.mark_message_read(account, provider_message_id)
        elif account["provider"] == "yandex":
            await sync_yandex.mark_message_read(account, provider_message_id)
        else:
            return
        logger.info(
            "Marked %s message %s as read on provider",
            account["provider"], provider_message_id,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort by design
        logger.warning(
            "Provider mark-read failed for %s (%s): %s",
            account.get("email"), account.get("provider"), exc,
        )


def spawn_mark_read(db: Database, account_id: int, provider_message_id: str) -> None:
    """Fire-and-forget provider mark-read (keeps the API response fast)."""
    task = asyncio.create_task(
        mark_read_on_provider(db, account_id, provider_message_id)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
