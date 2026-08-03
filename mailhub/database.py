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
from .compression import compress_text, decompress_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('ru', 'en')),
    -- 0 until the user picks a language once in /start; the selection is
    -- offered only on the very first run, never again
    language_chosen INTEGER NOT NULL DEFAULT 0,
    -- legacy column: interval is fully automatic now (elastic 10s..5min),
    -- nothing writes it anymore; CHECK kept for schema stability
    polling_interval_seconds INTEGER NOT NULL DEFAULT 300
        CHECK(polling_interval_seconds BETWEEN 10 AND 1800),
    muted_categories TEXT NOT NULL DEFAULT '[]',
    muted_senders TEXT NOT NULL DEFAULT '[]',
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
    body_html TEXT,
    -- category is a free-form string: built-in buckets (important, promo,
    -- spam, social, other) plus provider user labels surfaced as categories
    category TEXT NOT NULL,
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
        # Repair an interrupted legacy migration that left child tables
        # pointing at a dropped users_old table. This was observed in the VPS
        # database and prevents every account/update query from working.
        await self._repair_user_foreign_keys()

        await self._migrate_messages_cache()
        await self._ensure_column(
            "mail_accounts", "unread_bootstrap_done", "BOOLEAN NOT NULL DEFAULT 0"
        )
        await self._ensure_column("users", "muted_senders", "TEXT NOT NULL DEFAULT '[]'")
        await self._ensure_column(
            "users", "language_chosen", "INTEGER NOT NULL DEFAULT 0"
        )
        await self._conn.commit()

    async def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        """Add a column in-place when the deployed database predates it."""
        columns = await self._conn.execute_fetchall(f"PRAGMA table_info({table})")
        if not any(row[1] == column for row in columns):
            await self._conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"
            )

    async def _migrate_messages_cache(self) -> None:
        """Rebuild messages_cache when its DDL no longer matches the current
        schema (dropped category CHECK + new body_html column), preserving
        every cached row. Also adds body_html when the table already matches."""
        table_sql = await self._fetchone(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'messages_cache'"
        )
        ddl = (table_sql or {}).get("sql") or ""
        if "CHECK(category" in ddl:
            await self._conn.execute("PRAGMA foreign_keys = OFF")
            await self._conn.execute(
                "ALTER TABLE messages_cache RENAME TO messages_cache_legacy"
            )
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
                    body_html TEXT,
                    category TEXT NOT NULL,
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
                    subject, snippet, body_text, body_html, category, received_at,
                    is_read, notified_at, created_at)
                   SELECT id, account_id, provider_message_id, sender_name, sender_email,
                          subject, snippet, body_text, NULL, category, received_at,
                          is_read, notified_at, created_at
                   FROM messages_cache_legacy"""
            )
            await self._conn.execute("DROP TABLE messages_cache_legacy")
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_account ON messages_cache(account_id)")
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_category ON messages_cache(category)")
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_received ON messages_cache(received_at)")
            await self._conn.execute("PRAGMA foreign_keys = ON")
            return
        await self._ensure_column("messages_cache", "body_html", "TEXT")

    async def _repair_user_foreign_keys(self) -> None:
        """Rebuild tables that reference a deleted ``users_old`` table.

        SQLite stores foreign-key targets in table DDL, so creating the
        current schema with ``IF NOT EXISTS`` cannot repair a half-completed
        rename migration. Rebuild only when either child explicitly points at
        the missing/legacy parent; all rows are copied before the old tables
        are dropped.
        """
        account_sql = await self._fetchone(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'mail_accounts'"
        )
        oauth_sql = await self._fetchone(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'oauth_states'"
        )
        needs_repair = any(
            row and "users_old" in (row["sql"] or "")
            for row in (account_sql, oauth_sql)
        )
        if not needs_repair:
            return

        account_columns = await self._conn.execute_fetchall("PRAGMA table_info(mail_accounts)")
        existing_account_columns = {row[1] for row in account_columns}
        account_fields = [
            "id", "user_id", "provider", "email", "encrypted_access_token",
            "encrypted_refresh_token", "token_expires_at", "last_checkpoint",
            "is_active", "sync_error_count", "next_sync_at", "created_at",
        ]
        account_select = [
            field if field in existing_account_columns else "NULL AS " + field
            for field in account_fields
        ]
        if "unread_bootstrap_done" in existing_account_columns:
            account_select.append("unread_bootstrap_done")
        else:
            account_select.append("0 AS unread_bootstrap_done")

        await self._conn.execute("PRAGMA foreign_keys = OFF")
        await self._conn.execute("BEGIN")
        try:
            await self._conn.execute(
                """CREATE TABLE mail_accounts_repaired (
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
                    unread_bootstrap_done BOOLEAN NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, email)
                )"""
            )
            await self._conn.execute(
                """INSERT INTO mail_accounts_repaired
                   (id, user_id, provider, email, encrypted_access_token,
                    encrypted_refresh_token, token_expires_at, last_checkpoint,
                    is_active, sync_error_count, next_sync_at, created_at,
                    unread_bootstrap_done)
                   SELECT """ + ", ".join(account_select) + " FROM mail_accounts"
            )
            await self._conn.execute(
                """CREATE TABLE oauth_states_repaired (
                    state TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )"""
            )
            await self._conn.execute(
                """INSERT INTO oauth_states_repaired (state, user_id, provider, created_at)
                   SELECT state, user_id, provider, created_at FROM oauth_states"""
            )
            await self._conn.execute("DROP TABLE oauth_states")
            await self._conn.execute("DROP TABLE mail_accounts")
            await self._conn.execute("ALTER TABLE mail_accounts_repaired RENAME TO mail_accounts")
            await self._conn.execute("ALTER TABLE oauth_states_repaired RENAME TO oauth_states")
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user ON mail_accounts(user_id)")
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_next_sync ON mail_accounts(next_sync_at)")
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise
        finally:
            await self._conn.execute("PRAGMA foreign_keys = ON")

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
    def _decompress_row(row: dict) -> dict:
        """Decompress the body fields of a messages_cache row in place.

        Body blobs are transparently compressed with zstd before storage;
        every read path that returns message rows funnels through this so
        callers always see plain text. Legacy plain-text rows pass through
        unchanged.
        """
        if row.get("body_text") is not None:
            row["body_text"] = decompress_text(row["body_text"])
        if row.get("body_html") is not None:
            row["body_html"] = decompress_text(row["body_html"])
        return row

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
        """Set the user's language and mark the one-time language choice as done."""
        await self._execute(
            "UPDATE users SET language = ?, language_chosen = 1 WHERE telegram_id = ?",
            (language, telegram_id),
        )

    async def get_user_categories(self, user_id: int) -> list[str]:
        """Categories visible to the user: built-in buckets plus any custom
        provider labels that appeared in their cached mail (union across all
        connected accounts). Re-fetched on every settings open."""
        rows = await self._fetchall(
            """SELECT DISTINCT mc.category AS category
               FROM messages_cache mc
               JOIN mail_accounts a ON a.id = mc.account_id
               WHERE a.user_id = ? AND mc.category NOT IN ('promo', 'spam')
               ORDER BY mc.category""",
            (user_id,),
        )
        defaults = ["important", "social", "other"]
        return list(dict.fromkeys(defaults + [r["category"] for r in rows]))

    async def get_settings(self, telegram_id: int) -> dict:
        user = await self.get_user(telegram_id)
        if user is None:
            return {
                "language": "en",
                "muted_categories": [],
                "muted_senders": [],
                "categories": ["important", "social", "other"],
            }
        return {
            "language": user["language"],
            "muted_categories": json.loads(user["muted_categories"] or "[]"),
            "muted_senders": json.loads(user["muted_senders"] or "[]"),
            "categories": await self.get_user_categories(telegram_id),
        }

    async def update_settings(
        self,
        telegram_id: int,
        language: str | None = None,
        muted_categories: list[str] | None = None,
    ) -> dict:
        """Update user settings. The polling interval is NOT user-configurable:
        it is fixed at 10 seconds from account addition."""
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

    async def get_muted_senders(self, telegram_id: int) -> list[str]:
        user = await self.get_user(telegram_id)
        if user is None:
            return []
        return json.loads(user["muted_senders"] or "[]")

    async def add_muted_sender(self, telegram_id: int, email: str) -> None:
        """Hide all mail from a sender (lower-cased) for this user."""
        email = email.strip().lower()
        if not email:
            return
        muted = await self.get_muted_senders(telegram_id)
        if email in muted:
            return
        muted.append(email)
        await self._execute(
            "UPDATE users SET muted_senders = ? WHERE telegram_id = ?",
            (json.dumps(muted), telegram_id),
        )

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
        # Normalize to lowercase so the same mailbox can never be stored twice
        # with different casing (the unique index is byte-sensitive).
        email = email.strip().lower()
        await self._execute(
            """INSERT OR IGNORE INTO mail_accounts
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
                      u.muted_senders AS user_muted_senders,
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
        snippet: str | None, body_text: str | None, body_html: str | None = None,
        provider_message_id: str = "",
    ) -> None:
        """Refresh a cached row when the provider returns it again."""
        await self._execute(
            """UPDATE messages_cache
               SET sender_name = ?, sender_email = ?, subject = ?, snippet = ?,
                   body_text = ?, body_html = ?, category = ?, received_at = ?,
                   is_read = ?
               WHERE id = ?""",
            (
                sender_name, sender_email, subject, snippet,
                compress_text(body_text) if body_text is not None else None,
                compress_text(body_html) if body_html is not None else None,
                category, received_at, int(is_read), message_id,
            ),
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
        body_html: str | None = None,
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
                subject, snippet, body_text, body_html, category, received_at,
                is_read)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                account_id,
                provider_message_id,
                sender_name,
                sender_email,
                subject,
                snippet,
                compress_text(body_text) if body_text is not None else None,
                compress_text(body_html) if body_html is not None else None,
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
        muted_senders: list[str] | None = None,
    ) -> list[dict]:
        sql = "SELECT * FROM messages_cache WHERE account_id = ?"
        params: list[Any] = [account_id]
        sql += " AND category NOT IN ('promo', 'spam')"
        if category:
            if category in SUPPRESSED_NOTIFICATION_CATEGORIES:
                return []
            sql += " AND category = ?"
            params.append(category)
        if muted_senders:
            placeholders = ",".join("?" for _ in muted_senders)
            sql += (
                " AND (sender_email IS NULL OR LOWER(sender_email) NOT IN ("
                + placeholders + "))"
            )
            params.extend(muted_senders)
        sql += " ORDER BY received_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [
            self._decompress_row(row)
            for row in await self._fetchall(sql, params)
        ]

    async def get_message(self, message_id: int, account_id: int | None = None) -> dict | None:
        if account_id is not None:
            row = await self._fetchone(
                "SELECT * FROM messages_cache WHERE id = ? AND account_id = ?",
                (message_id, account_id),
            )
        else:
            row = await self._fetchone(
                "SELECT * FROM messages_cache WHERE id = ?", (message_id,)
            )
        return self._decompress_row(row) if row else None

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
        return [
            self._decompress_row(row)
            for row in await self._fetchall(
                """SELECT * FROM messages_cache
                   WHERE account_id = ? AND notified_at IS NULL
                   ORDER BY received_at ASC LIMIT ?""",
                (account_id, limit),
            )
        ]

    async def mark_read(self, message_id: int) -> None:
        await self._execute(
            "UPDATE messages_cache SET is_read = 1 WHERE id = ?", (message_id,)
        )

    async def mark_notified(self, message_id: int) -> None:
        await self._execute(
            "UPDATE messages_cache SET notified_at = ? WHERE id = ?",
            (self._now(), message_id),
        )

    async def delete_message(self, message_id: int) -> bool:
        cur = await self._execute(
            "DELETE FROM messages_cache WHERE id = ?", (message_id,)
        )
        return cur.rowcount > 0

    async def delete_messages_from_sender(self, user_id: int, email: str) -> int:
        """Remove every cached message from a sender across all of the user's
        accounts (used by the 'hide messages from <email>' action)."""
        email = email.strip().lower()
        cur = await self._execute(
            """DELETE FROM messages_cache WHERE account_id IN (
                   SELECT id FROM mail_accounts WHERE user_id = ?
               ) AND LOWER(sender_email) = ?""",
            (user_id, email),
        )
        return cur.rowcount

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
