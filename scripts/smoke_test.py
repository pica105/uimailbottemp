"""End-to-end smoke test for the MailHub backend core.

Run from the project root with the venv active:
    ./.venv/bin/python scripts/smoke_test.py

Covers: config loading, crypto roundtrip, database schema + queries,
classifier heuristics, initData HMAC validation, and OAuth URL building.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from cryptography.fernet import Fernet

os.environ.setdefault("BOT_TOKEN", "123456:test-token-abc")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mailhub import sync_gmail  # noqa: E402
from mailhub.classifier import classify_yandex_message  # noqa: E402
from mailhub.config import get_settings  # noqa: E402
from mailhub.crypto import decrypt, encrypt  # noqa: E402
from mailhub.database import Database  # noqa: E402
from mailhub.oauth_server import validate_init_data  # noqa: E402
from mailhub.bot_handlers import (  # noqa: E402
    build_oauth_url,
    configure_menu_button,
    i18n,
    main_menu_keyboard,
)
from aiogram.types import MenuButtonWebApp, ReplyKeyboardMarkup  # noqa: E402


def test_crypto() -> None:
    secret = "ya29.a0AfH6SMDa-secret-token-value"
    encrypted = encrypt(secret)
    assert encrypted != secret
    assert decrypt(encrypted) == secret
    assert decrypt("") == ""
    assert decrypt("garbage-not-valid") == ""
    print("  ✓ crypto roundtrip")


def test_classifier() -> None:
    from email.message import Message

    msg = Message()
    msg["List-Unsubscribe"] = "<https://example.com/unsub>"
    msg["Subject"] = "Weekly digest"
    assert classify_yandex_message(msg) == "promo"

    msg2 = Message()
    msg2["From"] = "newsletter@example.com"
    msg2["Subject"] = "Hello"
    assert classify_yandex_message(msg2) == "promo"

    msg3 = Message()
    msg3["Subject"] = "Скидка 50% только сегодня!"
    assert classify_yandex_message(msg3) == "spam"

    msg4 = Message()
    msg4["From"] = "notifications@linkedin.com"
    msg4["Subject"] = "You have a new connection"
    assert classify_yandex_message(msg4) == "social"

    msg5 = Message()
    msg5["From"] = "alice@example.com"
    msg5["Subject"] = "Meeting tomorrow"
    assert classify_yandex_message(msg5) == "important"
    print("  ✓ classifier heuristics")


def test_database() -> None:
    db = Database(":memory:")
    asyncio.run(_db_scenario(db))
    print("  ✓ database schema + queries")


async def _db_scenario(db: Database) -> None:
    await db.connect()
    user = await db.get_or_create_user(42, username="alice", first_name="Alice", last_name="A")
    assert user["telegram_id"] == 42
    assert user["language"] == "en"
    # Language is chosen exactly once: the flag starts off and flips on choice.
    assert user["language_chosen"] == 0
    await db.set_language(42, "ru")
    user = await db.get_user(42)
    assert user is not None and user["language_chosen"] == 1
    assert (await db.get_settings(42))["language"] == "ru"

    await db.update_settings(42, muted_categories=["promo"])
    settings_row = await db.get_settings(42)
    # No polling-interval setting is exposed: the interval is fixed at 10s.
    assert "polling_interval_seconds" not in settings_row
    assert settings_row["muted_categories"] == ["promo"]
    assert settings_row["categories"] == ["important", "social", "other"]

    acc = await db.add_account(
        42, "gmail", "alice@gmail.com", encrypt("tok"), encrypt("ref"), 9999999999
    )
    assert acc["email"] == "alice@gmail.com"

    inserted = await db.upsert_message(
        acc["id"], "gmail-1",
        sender_name="Bob", sender_email="bob@example.com",
        subject="Hi", snippet="Hello world", body_text="Hello world full",
        category="important", received_at=1000,
    )
    assert inserted is True
    dup = await db.upsert_message(
        acc["id"], "gmail-1",
        sender_name="Bob", sender_email="bob@example.com",
        subject="Hi", snippet="Hello world", body_text="Hello world full",
        category="important", received_at=1000,
    )
    assert dup is False  # INSERT OR IGNORE

    messages = await db.get_messages(acc["id"])
    assert len(messages) == 1
    assert messages[0]["category"] == "important"

    social_inserted = await db.upsert_message(
        acc["id"], "social-1",
        sender_name="Network", sender_email="notifications@linkedin.com",
        subject="New connection", snippet="", body_text="",
        category="social", received_at=1100,
    )
    # Custom provider labels become categories and show up in settings.
    custom_inserted = await db.upsert_message(
        acc["id"], "gmail-trip",
        sender_name="Travel", sender_email="travel@example.com",
        subject="Your trip", snippet="", body_text="",
        category="trip", received_at=1150,
    )
    assert custom_inserted is True
    assert "trip" in await db.get_user_categories(42)
    assert [m["category"] for m in await db.get_messages(acc["id"], category="trip")] == ["trip"]
    assert [m["category"] for m in await db.get_messages(acc["id"])] == [
        "trip", "social", "important",
    ]
    # Muted senders hide messages from the list and can be removed.
    hidden_inserted = await db.upsert_message(
        acc["id"], "gmail-spam", sender_name="Spammer",
        sender_email="spammer@example.com", subject="Ad", snippet="",
        body_text="", category="important", received_at=1050,
    )
    assert hidden_inserted is True
    await db.add_muted_sender(42, "Spammer@Example.COM")
    assert await db.get_muted_senders(42) == ["spammer@example.com"]
    filtered = await db.get_messages(
        acc["id"], muted_senders=["spammer@example.com"]
    )
    assert all(m["sender_email"] != "spammer@example.com" for m in filtered)
    assert await db.delete_messages_from_sender(42, "spammer@example.com") == 1
    assert social_inserted is True

    promo_inserted = await db.upsert_message(
        acc["id"], "promo-1", sender_name="Promo", sender_email="promo@example.com",
        subject="Sale", snippet="", body_text="", category="promo", received_at=1200,
    )
    assert promo_inserted is True
    assert all(m["category"] != "promo" for m in await db.get_messages(acc["id"]))

    # A duplicate (case-variant) email must never create a second account.
    dup_acc = await db.add_account(
        42, "gmail", "ALICE@gmail.COM", encrypt("tok"), encrypt("ref"), 0,
    )
    assert dup_acc["id"] == acc["id"]

    await db.mark_read(messages[0]["id"])
    fetched = await db.get_message(messages[0]["id"])
    assert fetched is not None and fetched["is_read"] == 1

    # OAuth state TTL
    await db.save_oauth_state("state-1", 42, "gmail")
    row = await db.get_oauth_state("state-1")
    assert row is not None and row["provider"] == "gmail"
    await db.delete_oauth_state("state-1")
    assert await db.get_oauth_state("state-1") is None

    deleted = await db.delete_account(acc["id"], 42)
    assert deleted is True
    assert await db.get_account(acc["id"]) is None
    assert await db.get_message_count(acc["id"]) == 0

    await db.close()


def test_legacy_users_old_repair() -> None:
    """Repair the interrupted VPS migration without losing cached data."""
    path = Path(tempfile.mktemp(suffix=".db"))
    conn = sqlite3.connect(path)
    conn.executescript(
        """PRAGMA foreign_keys = OFF;
        CREATE TABLE users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            language TEXT NOT NULL DEFAULT 'en',
            polling_interval_seconds INTEGER NOT NULL DEFAULT 300,
            muted_categories TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE mail_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users_old(telegram_id) ON DELETE CASCADE,
            provider TEXT NOT NULL CHECK(provider IN ('gmail', 'yandex')),
            email TEXT NOT NULL,
            encrypted_access_token TEXT NOT NULL,
            encrypted_refresh_token TEXT,
            token_expires_at TIMESTAMP,
            last_checkpoint TEXT,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            sync_error_count INTEGER NOT NULL DEFAULT 0,
            next_sync_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, email)
        );
        CREATE TABLE messages_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES mail_accounts(id) ON DELETE CASCADE,
            provider_message_id TEXT NOT NULL,
            sender_name TEXT,
            sender_email TEXT,
            subject TEXT,
            snippet TEXT,
            body_text TEXT,
            category TEXT NOT NULL CHECK(category IN ('important', 'promo', 'spam', 'other')),
            received_at TIMESTAMP NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT 0,
            notified_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, provider_message_id)
        );
        CREATE TABLE oauth_states (
            state TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users_old(telegram_id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        INSERT INTO users (telegram_id, username) VALUES (77, 'legacy');
        INSERT INTO mail_accounts
            (id, user_id, provider, email, encrypted_access_token,
             encrypted_refresh_token, token_expires_at, last_checkpoint,
             is_active, sync_error_count, next_sync_at, created_at)
            VALUES (7, 77, 'gmail', 'legacy@example.com', 'token', 'refresh',
                    NULL, NULL, 1, 0, NULL, CURRENT_TIMESTAMP);
        INSERT INTO messages_cache
            (account_id, provider_message_id, subject, category, received_at)
            VALUES (7, 'legacy-1', 'Legacy mail', 'important', 100);
        INSERT INTO oauth_states (state, user_id, provider, created_at)
            VALUES ('legacy-state', 77, 'gmail', strftime('%s', 'now'));
        """
    )
    conn.commit()
    conn.close()

    async def scenario() -> None:
        db = Database(path)
        try:
            await db.connect()
            account = await db.get_account(7)
            messages = await db.get_messages(7)
            oauth_state = await db.get_oauth_state("legacy-state")
            foreign_key_errors = await db._fetchall("PRAGMA foreign_key_check")
            assert account is not None
            assert len(messages) == 1 and messages[0]["subject"] == "Legacy mail"
            assert oauth_state is not None
            assert foreign_key_errors == []
            assert await db.delete_account(7, 77) is True
            assert await db.get_account(7) is None
        finally:
            await db.close()

    try:
        asyncio.run(scenario())
    finally:
        path.unlink(missing_ok=True)
    print("  ✓ legacy users_old foreign-key migration + data preservation")


def test_init_data() -> None:
    settings = get_settings()
    token = settings.BOT_TOKEN
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    user = {"id": 42, "first_name": "Alice"}
    auth_date = int(time.time())
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAFkZmVhAAAAAGRmZWEAAImluLY",
        "user": json.dumps(user),
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    hash_val = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    init_data = "&".join(f"{k}={v}" for k, v in fields.items()) + f"&hash={hash_val}"

    parsed = validate_init_data(init_data, max_age_seconds=86400)
    assert parsed is not None, "valid initData should pass"
    assert int(parsed["auth_date"]) == auth_date

    assert validate_init_data("hash=deadbeef") is None
    assert validate_init_data("") is None

    # Tampered data must fail.
    tampered = init_data.replace('"id": 42', '"id": 43')
    assert validate_init_data(tampered, max_age_seconds=86400) is None
    print("  ✓ initData HMAC validation")


def test_bot_navigation() -> None:
    """Root navigation uses reply buttons; Mini App uses chat menu button."""
    for lang in ("ru", "en"):
        keyboard = main_menu_keyboard(lang)
        assert isinstance(keyboard, ReplyKeyboardMarkup)
        assert keyboard.resize_keyboard is True
        assert keyboard.is_persistent is True
        assert i18n.t(lang, "btn_accounts") in {
            button.text for row in keyboard.keyboard for button in row
        }
        menu_button = configure_menu_button(lang)
        assert isinstance(menu_button, MenuButtonWebApp)
        assert menu_button.type == "web_app"
        assert menu_button.web_app.url.startswith("https://")
        # The main menu no longer advertises the Mini App button.
        assert "Mini App" not in i18n.t(lang, "main_menu")
    print("  ✓ Telegram reply navigation + Mini App menu button")


def test_oauth_urls() -> None:
    url = build_oauth_url("gmail", "state123")
    assert "accounts.google.com" in url
    assert "state123" in url
    url2 = build_oauth_url("yandex", "state456")
    assert "oauth.yandex.ru" in url2
    assert "state456" in url2
    # Yandex scopes: space-separated, URL-encoded. Guard against regressions
    # to the retired `imap:full_mailbox` scope name.
    assert "scope=login:email%20mail:imap_full" in url2
    assert "imap:full_mailbox" not in url2
    print("  ✓ OAuth URL builders")


def test_gmail_helpers() -> None:
    name, email = sync_gmail._split_sender('"John Doe" <john@example.com>')
    assert name == "John Doe" and email == "john@example.com"
    assert sync_gmail._split_sender("bare@example.com") == (None, "bare@example.com")
    # User labels surface as custom categories; built-in labels do not.
    assert sync_gmail._category_from_labels(["INBOX", "UNREAD", "Trip 2026"]) == "trip-2026"
    assert sync_gmail._category_from_labels(["INBOX", "CATEGORY_SOCIAL"]) == "social"
    assert sync_gmail._category_from_labels(["INBOX"]) == "important"
    # Label_<id> resolves through the fetched label-names map.
    names = {"Label_5": "Trip", "Label_9": "Работа"}
    assert sync_gmail._category_from_labels(["INBOX", "Label_5"], names) == "trip"
    assert sync_gmail._category_from_labels(["INBOX", "Label_9"], names) == "работа"
    assert sync_gmail._category_from_labels(["INBOX", "Label_5"]) == "important"
    print("  ✓ gmail helpers")


def test_yandex_parsing() -> None:
    import base64
    import email as email_mod

    from mailhub.sync_yandex import _decode_header_value, _html_to_text, _message_to_record

    # RFC 2047 encoded-word subject decoding
    enc = base64.b64encode("Привет, мир".encode("utf-8")).decode("ascii")
    assert _decode_header_value(f"=?utf-8?b?{enc}?=") == "Привет, мир"

    # HTML → text fallback (skips script content)
    html = "<html><body><p>Hello <b>world</b>!</p><script>alert(1)</script></body></html>"
    text = _html_to_text(html)
    assert "Hello world" in text
    assert "alert" not in text

    # Full record from a raw message (encoded headers + plain body)
    name_enc = base64.b64encode("Тестер".encode("utf-8")).decode("ascii")
    raw = (
        f"From: =?utf-8?b?{name_enc}?= <tester@example.com>\r\n"
        "To: a@b.c\r\n"
        f"Subject: =?utf-8?b?{enc}?=\r\n"
        "Date: Tue, 01 Aug 2026 12:00:00 +0300\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Тело письма"
    )
    msg = email_mod.message_from_bytes(raw.encode("utf-8"))
    rec = _message_to_record(7, msg)
    assert rec is not None
    assert rec["subject"] == "Привет, мир"
    assert rec["sender_name"] == "Тестер"
    assert rec["sender_email"] == "tester@example.com"
    assert rec["body_text"] == "Тело письма"
    assert rec["provider_message_id"] == "yandex-7"
    assert rec["received_at"] > 0
    print("  ✓ yandex message parsing (decoding + html fallback)")


def test_fixed_poll_interval() -> None:
    """Polling is fixed at 10 seconds per account from addition."""
    from mailhub.config import settings as cfg
    from mailhub.sync_engine import fixed_poll_interval

    assert cfg.POLL_FIXED_SECONDS == 10
    assert fixed_poll_interval() == 10
    print("  ✓ fixed polling interval (10s, from account addition)")


def test_settings_keyboard_layout() -> None:
    """Settings keyboard: language pair, blacklist row, category pairs,
    and 'Open' paired with a leftover odd category or alone otherwise."""
    from mailhub.bot_handlers import settings_keyboard

    # 3 categories (odd) → last category shares a row with Open
    kb = settings_keyboard("ru", ["important"], ["important", "social", "trip"])
    rows = kb.inline_keyboard
    assert [len(r) for r in rows] == [2, 1, 2, 2]
    assert rows[0][0].callback_data == "settings:lang:ru"
    assert rows[1][0].callback_data == "settings:blacklist"
    # odd category + Open share the final row of width 2
    assert rows[-1][0].callback_data == "settings:mute:trip"
    assert rows[-1][1].web_app is not None
    assert rows[-1][1].web_app.url.endswith("/settings")

    # 2 categories (even) → Open sits alone
    kb2 = settings_keyboard("en", [], ["important", "social"])
    rows2 = kb2.inline_keyboard
    assert [len(r) for r in rows2] == [2, 1, 2, 1]
    assert rows2[-1][0].web_app is not None

    # 1 category → pairs with Open; 0 categories → Open alone
    assert [len(r) for r in settings_keyboard("en", [], ["other"]).inline_keyboard] == [2, 1, 2]
    assert [len(r) for r in settings_keyboard("en", [], []).inline_keyboard] == [2, 1, 1]
    print("  ✓ settings keyboard layout")


def test_notification_builder() -> None:
    """Rich notification: plain header, inline hyperlinks, bare-URL
    shortening, 250-char preview collapse, and image extraction."""
    from mailhub.bot_handlers import build_notification, notification_keyboard
    from mailhub.html_email import convert_body, shorten_url_display

    assert shorten_url_display("https://a.co/x") == "a.co/x"
    assert shorten_url_display("https://www.example.com/very/long/url") == "www.examp..."

    html = (
        "<p>Hello <a href=\"https://example.com/x\">there</a>!</p>"
        "<p>Check https://www.example.com/some/very/long/path now</p>"
        "<img src=\"https://cdn.example.com/pic.png\">"
    )
    text, image = convert_body(html, None, None)
    assert image == "https://cdn.example.com/pic.png"
    assert "<a href=\"https://example.com/x\">there</a>" in text
    assert "www.examp..." in text

    msg = {
        "id": 9,
        "sender_name": "SpaceXAI",
        "sender_email": "noreply@x.ai",
        "subject": "New login",
        "body_text": "*Time:* Mon, 3 Aug 2026 15:33:52 +0000\n*IP:* 89.105.200.140",
        "body_html": None,
    }
    text, image, truncated = build_notification(msg)
    assert text.startswith("✉️ SpaceXAI")
    assert "New login" in text
    assert "89.105.200.140" in text
    assert image is None and truncated is False

    long_body = "word " * 120
    long_msg = {**msg, "body_text": long_body}
    _text, _image, truncated = build_notification(long_msg)
    assert truncated is True
    assert len(_text) <= 260

    kb = notification_keyboard(9, "ru", "gmail", state="trunc")
    assert [len(row) for row in kb.inline_keyboard] == [2, 1]
    kb_actions = notification_keyboard(
        9, "ru", "yandex", actions=True, state="exp",
        sender_email="noreply@x.ai", provider_message_id="yandex-7",
    )
    assert [len(row) for row in kb_actions.inline_keyboard] == [1, 1, 3]
    # The display state is carried so in-place edits can rebuild the text.
    assert kb_actions.inline_keyboard[2][0].callback_data == "msg:back:9:exp"
    # 'Open' in a notification deep-links to the message, not to settings.
    assert kb.inline_keyboard[1][0].web_app.url.endswith("/message/9")
    print("  ✓ rich notification builder (links, preview, buttons)")


if __name__ == "__main__":
    print("Running MailHub backend smoke tests...")
    test_crypto()
    test_classifier()
    test_database()
    test_legacy_users_old_repair()
    test_init_data()
    test_bot_navigation()
    test_oauth_urls()
    test_gmail_helpers()
    test_yandex_parsing()
    test_fixed_poll_interval()
    test_settings_keyboard_layout()
    test_notification_builder()
    print("\nAll smoke tests passed ✅")
