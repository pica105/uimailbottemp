"""Async SQLite data access layer (aiosqlite).

Owns schema creation and every SQL query used by the bot, OAuth server,
and sync engine. Single connection shared across the process (SQLite
serializes writes; aiosqlite runs it on a background thread).
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Iterable

import aiosqlite

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('ru', 'en')),
    -- legacy column: interval is fully automatic now (elastic 10s..5min),
    -- nothing writes it anymore; CHECK kept for schema stability
    polling_interval_seconds INTEGER NOT NULL DEFAULT 300
        CHECK(polling_interval_seconds BETWEEN 10 AND 1800),
    muted_categories TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mail_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK(provider IN ('gmail', 'yandex')),
    email TEXT NOT NULL,
    encrypted_access_token TEXT NOT NULL,
    encrypted_refresh_token TEXT,
    token_expires_at TIMESTAMP,
    last_checkpoint TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    sync_error_count INTEGER NOT NULL DEFAULT 0,
    next_sync_at TIMESTAMP,
    -- One-time provider-side backfill of the latest unread messages.
    unread_bootstrap_done BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, email)
);
CREATE INDEX IF NOT EXISTS idx_accounts_user ON mail_accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_accounts_next_sync ON mail_accounts(next_sync_at);

CREATE TABLE IF NOT EXISTS messages_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES mail_accounts(id) ON DELETE CASCADE,
    provider_message_id TEXT NOT NULL,
    sender_name TEXT,
    sender_email TEXT,
    subject TEXT,
    snippet TEXT,
    body_text TEXT,
    category TEXT NOT NULL CHECK(category IN ('important', 'promo', 'spam', 'social', 'other')),
    received_at TIMESTAMP NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT 0,
    notified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, provider_message_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_account ON messages_cache(account_id);
CREATE INDEX IF NOT EXISTS idx_messages_category ON messages_cache(category);
CREATE INDEX IF NOT EXISTS idx_messages_received ON messages_cache(received_at);

CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""

CATEGORIES = ("important", "promo", "spam", "social", "other")

# Promo and spam remain stored for backwards-compatible cache rows, but they
# are never shown in the Mini App or sent as Telegram notifications.
SUPPRESSED_NOTIFICATION_CATEGORIES = frozenset({"promo", "spam"})


class Database:
    """Thin async wrapper around a single SQLite connection."""

    def __init__(self, path: str | None = None) -> None:
        self._path = str(path or settings.DB_PATH)
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.executescript(SCHEMA)
        # Existing VPS databases used a CHECK constraint without `social`.
        # Rebuild only that cache table in-place, preserving all cached rows.
        table_sql = await self._fetchone(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'messages_cache'"
        )
        if table_sql and "'social'" not in (table_sql["sql"] or ""):
            await self._conn.execute("PRAGMA foreign_keys = OFF")
            await self._conn.execute("ALTER TABLE messages_cache RENAME TO messages_cache_legacy")
            await self._conn.execute(
                """CREATE TABLE messages_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL REFERENCES mail_accounts(id) ON DELETE CASCADE,
                    provider_message_id TEXT NOT NULL,
                    sender_name TEXT,
                    sender_email TEXT,
                    subject TEXT,
                    snippet TEXT,
                    body_text TEXT,
                    category TEXT NOT NULL CHECK(category IN ('important', 'promo', 'spam', 'social', 'other')),
                    received_at TIMESTAMP NOT NULL,
                    is_read BOOLEAN NOT NULL DEFAULT 0,
                    notified_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(account_id, provider_message_id)
                )"""
            )
            await self._conn.execute(
                """INSERT INTO messages_cache
                   (id, account_id, provider_message_id, sender_name, sender_email,
                    subject, snippet, body_text, category, received_at, is_read,
                    notified_at, created_at)
                   SELECT id, account_id, provider_message_id, sender_name, sender_email,
                          subject, snippet, body_text, category, received_at, is_read,
                          notified_at, created_at
                   FROM messages_cache_legacy"""
            )
            await self._conn.execute("DROP TABLE messages_cache_legacy")
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_account ON messages_cache(account_id)")
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_category ON messages_cache(category)")
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_received ON messages_cache(received_at)")
            await self._conn.execute("PRAGMA foreign_keys = ON")

        # Existing VPS databases were created before unread bootstrap existed.
        # Add the column in-place so deployment needs no destructive migration.
        columns = await self._conn.execute_fetchall("PRAGMA table_info(mail_accounts)")
        if not any(row[1] == "unread_bootstrap_done" for row in columns):
            await self._conn.execute(
                "ALTER TABLE mail_accounts ADD COLUMN unread_bootstrap_done "
                "BOOLEAN NOT NULL DEFAULT 0"
            )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _fetchone(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        cur = await self.conn.execute(sql, tuple(params))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

    async def _fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        cur = await self.conn.execute(sql, tuple(params))
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def _execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        cur = await self.conn.execute(sql, tuple(params))
        await self.conn.commit()
        return cur

    @staticmethod
    def _now() -> int:
        return int(time.time())

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    async def get_user(self, telegram_id: int) -> dict | None:
        return await self._fetchone(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )

    async def create_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> dict:
        await self._execute(
            """INSERT OR IGNORE INTO users
               (telegram_id, username, first_name, last_name)
               VALUES (?, ?, ?, ?)""",
            (telegram_id, username, first_name, last_name),
        )
        user = await self.get_user(telegram_id)
        assert user is not None
        return user

    async def get_or_create_user(self, telegram_id: int, **profile: str | None) -> dict:
        user = await self.get_user(telegram_id)
        if user is not None:
            return user
        return await self.create_user(telegram_id, profile.get("username"), profile.get("first_name"), profile.get("last_name"))

    async def set_language(self, telegram_id: int, language: str) -> None:
        await self._execute(
            "UPDATE users SET language = ? WHERE telegram_id = ?",
            (language, telegram_id),
        )

    async def get_settings(self, telegram_id: int) -> dict:
        user = await self.get_user(telegram_id)
        if user is None:
            return {
                "language": "en",
                "polling_interval_seconds": 300,
                "muted_categories": [],
            }
        return {
            "language": user["language"],
            "polling_interval_seconds": user["polling_interval_seconds"],
            "muted_categories": json.loads(user["muted_categories"] or "[]"),
        }

    async def update_settings(
        self,
        telegram_id: int,
        language: str | None = None,
        muted_categories: list[str] | None = None,
    ) -> dict:
        """Update user settings. The polling interval is deliberately NOT
        user-configurable: it is fully automatic (elastic 10s..5min)."""
        fields: list[str] = []
        params: list[Any] = []
        if language is not None:
            fields.append("language = ?")
            params.append(language)
        if muted_categories is not None:
            fields.append("muted_categories = ?")
            params.append(json.dumps(muted_categories))
        if fields:
            params.append(telegram_id)
            await self._execute(
                f"UPDATE users SET {', '.join(fields)} WHERE telegram_id = ?", params
            )
        return await self.get_settings(telegram_id)

    # ------------------------------------------------------------------
    # Mail accounts
    # ------------------------------------------------------------------
    async def add_account(
        self,
        user_id: int,
        provider: str,
        email: str,
        encrypted_access_token: str,
        encrypted_refresh_token: str,
        token_expires_at: int | None = None,
    ) -> dict:
        await self._execute(
            """INSERT INTO mail_accounts
               (user_id, provider, email, encrypted_access_token,
                encrypted_refresh_token, token_expires_at, next_sync_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                provider,
                email,
                encrypted_access_token,
                encrypted_refresh_token,
                token_expires_at,
                self._now(),  # sync immediately after connect
            ),
        )
        return await self._fetchone(
            "SELECT * FROM mail_accounts WHERE user_id = ? AND email = ?",
            (user_id, email),
        ) or {}

    async def get_account(self, account_id: int) -> dict | None:
        return await self._fetchone(
            "SELECT * FROM mail_accounts WHERE id = ?", (account_id,)
        )

    async def get_accounts(self, user_id: int) -> list[dict]:
        return await self._fetchall(
            "SELECT * FROM mail_accounts WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        )

    async def get_active_accounts(self) -> list[dict]:
        """All active accounts with the owner's language and muted categories.

        Used by the sync engine so it can localize notifications.
        """
        return await self._fetchall(
            """SELECT a.*, u.language AS user_language,
                      u.muted_categories AS user_muted_categories,
                      u.polling_interval_seconds AS polling_interval_seconds,
                      u.telegram_id AS user_telegram_id
               FROM mail_accounts a
               JOIN users u ON u.telegram_id = a.user_id
               WHERE a.is_active = 1
               ORDER BY a.next_sync_at ASC"""
        )

    async def delete_account(self, account_id: int, user_id: int | None = None) -> bool:
        """Delete an account and its cached mail, optionally scoped to owner.

        Cached rows are removed explicitly before the parent row. This keeps
        unlink reliable for legacy SQLite databases whose foreign-key cascade
        was created incorrectly, while the current schema still has CASCADE.
        """
        account = await self.get_account(account_id)
        if account is None or (user_id is not None and account["user_id"] != user_id):
            return False
        await self._execute(
            "DELETE FROM messages_cache WHERE account_id = ?", (account_id,)
        )
        cur = await self._execute(
            "DELETE FROM mail_accounts WHERE id = ?", (account_id,)
        )
        return cur.rowcount > 0

    async def set_account_active(self, account_id: int, is_active: bool) -> None:
        await self._execute(
            "UPDATE mail_accounts SET is_active = ?, sync_error_count = 0 WHERE id = ?",
            (int(is_active), account_id),
        )

    async def update_account_tokens(
        self,
        account_id: int,
        encrypted_access_token: str,
        encrypted_refresh_token: str | None,
        token_expires_at: int | None,
    ) -> None:
        await self._execute(
            """UPDATE mail_accounts
               SET encrypted_access_token = ?, encrypted_refresh_token = ?,
                   token_expires_at = ?, sync_error_count = 0
               WHERE id = ?""",
            (encrypted_access_token, encrypted_refresh_token, token_expires_at, account_id),
        )

    async def set_checkpoint(self, account_id: int, checkpoint: str) -> None:
        await self._execute(
            "UPDATE mail_accounts SET last_checkpoint = ? WHERE id = ?",
            (checkpoint, account_id),
        )

    async def mark_unread_bootstrap_done(self, account_id: int) -> None:
        await self._execute(
            "UPDATE mail_accounts SET unread_bootstrap_done = 1 WHERE id = ?",
            (account_id,),
        )

    async def update_message_from_provider(
        self, message_id: int, *, is_read: bool, category: str, received_at: int,
        sender_name: str | None, sender_email: str | None, subject: str | None,
        snippet: str | None, body_text: str | None, provider_message_id: str,
    ) -> None:
        """Refresh a cached row when the provider returns it again."""
        await self._execute(
            """UPDATE messages_cache
               SET sender_name = ?, sender_email = ?, subject = ?, snippet = ?,
                   body_text = ?, category = ?, received_at = ?, is_read = ?
               WHERE id = ?""",
            (sender_name, sender_email, subject, snippet, body_text, category,
             received_at, int(is_read), message_id),
        )

    async def schedule_next_sync(self, account_id: int, interval_seconds: int) -> None:
        await self._execute(
            "UPDATE mail_accounts SET next_sync_at = ? WHERE id = ?",
            (self._now() + interval_seconds, account_id),
        )

    async def increment_error(self, account_id: int) -> None:
        """Bump sync_error_count and push next_sync_at with exponential backoff."""
        account = await self.get_account(account_id)
        if account is None:
            return
        count = account["sync_error_count"] + 1
        backoff = min(2**count * 60, settings.SYNC_ERROR_MAX_BACKOFF_SECONDS)
        await self._execute(
            """UPDATE mail_accounts
               SET sync_error_count = ?, next_sync_at = ?
               WHERE id = ?""",
            (count, self._now() + backoff, account_id),
        )

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    async def upsert_message(
        self,
        account_id: int,
        provider_message_id: str,
        *,
        sender_name: str | None,
        sender_email: str | None,
        subject: str | None,
        snippet: str | None,
        body_text: str | None,
        category: str,
        received_at: int,
        is_read: bool = False,
    ) -> bool:
        """Insert a message if new; returns True when a NEW message was stored.

        Used by the sync engine to decide whether to send a notification.
        """
        cur = await self._execute(
            """INSERT OR IGNORE INTO messages_cache
               (account_id, provider_message_id, sender_name, sender_email,
                subject, snippet, body_text, category, received_at, is_read)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                account_id,
                provider_message_id,
                sender_name,
                sender_email,
                subject,
                snippet,
                body_text,
                category,
                received_at,
                int(is_read),
            ),
        )
        return cur.rowcount > 0

    async def get_messages(
        self,
        account_id: int,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        sql = "SELECT * FROM messages_cache WHERE account_id = ?"
        params: list[Any] = [account_id]
        sql += " AND category NOT IN ('promo', 'spam')"
        if category and category in CATEGORIES:
            if category in SUPPRESSED_NOTIFICATION_CATEGORIES:
                return []
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY received_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return await self._fetchall(sql, params)

    async def get_message(self, message_id: int, account_id: int | None = None) -> dict | None:
        if account_id is not None:
            return await self._fetchone(
                "SELECT * FROM messages_cache WHERE id = ? AND account_id = ?",
                (message_id, account_id),
            )
        return await self._fetchone(
            "SELECT * FROM messages_cache WHERE id = ?", (message_id,)
        )

    async def get_message_count(self, account_id: int) -> int:
        """Number of cached messages for an account (0 = not yet imported)."""
        row = await self._fetchone(
            "SELECT COUNT(*) AS n FROM messages_cache WHERE account_id = ?",
            (account_id,),
        )
        return int((row or {}).get("n", 0))

    async def get_unread_message_count(self, account_id: int) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS n FROM messages_cache "
            "WHERE account_id = ? AND is_read = 0",
            (account_id,),
        )
        return int((row or {}).get("n", 0))

    async def get_last_message_at(self, account_id: int) -> int | None:
        """Timestamp of the newest cached message, or None when empty.

        Drives the elastic polling: the further in the past the newest
        message is, the longer the engine waits before the next check.
        """
        row = await self._fetchone(
            "SELECT MAX(received_at) AS last_at FROM messages_cache WHERE account_id = ?",
            (account_id,),
        )
        last_at = (row or {}).get("last_at")
        return int(last_at) if last_at is not None else None

    async def get_unnotified_messages(self, account_id: int, limit: int = 10) -> list[dict]:
        """Messages that have not been notified yet, oldest first.

        Used by the sync engine so that bursts of new mail are all
        delivered (not just the newest N).
        """
        return await self._fetchall(
            """SELECT * FROM messages_cache
               WHERE account_id = ? AND notified_at IS NULL
               ORDER BY received_at ASC LIMIT ?""",
            (account_id, limit),
        )

    async def mark_read(self, message_id: int) -> None:
        await self._execute(
            "UPDATE messages_cache SET is_read = 1 WHERE id = ?", (message_id,)
        )

    async def mark_notified(self, message_id: int) -> None:
        await self._execute(
            "UPDATE messages_cache SET notified_at = ? WHERE id = ?",
            (self._now(), message_id),
        )

    async def mark_all_notified(self, account_id: int) -> None:
        """Mark every un-notified message of an account as notified.

        Used by the sync engine to suppress the initial-import notification
        flood when a user connects an account with existing mail.
        """
        await self._execute(
            "UPDATE messages_cache SET notified_at = ? "
            "WHERE account_id = ? AND notified_at IS NULL",
            (self._now(), account_id),
        )

    # ------------------------------------------------------------------
    # OAuth state
    # ------------------------------------------------------------------
    async def save_oauth_state(self, state: str, user_id: int, provider: str) -> None:
        await self._execute(
            "INSERT OR REPLACE INTO oauth_states (state, user_id, provider, created_at) VALUES (?, ?, ?, ?)",
            (state, user_id, provider, self._now()),
        )

    async def get_oauth_state(self, state: str) -> dict | None:
        """Return the state if it exists and is younger than the TTL."""
        row = await self._fetchone(
            "SELECT * FROM oauth_states WHERE state = ?", (state,)
        )
        if row is None:
            return None
        if self._now() - row["created_at"] > settings.OAUTH_STATE_TTL_SECONDS:
            await self._execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            return None
        return row

    async def delete_oauth_state(self, state: str) -> None:
        await self._execute("DELETE FROM oauth_states WHERE state = ?", (state,))
