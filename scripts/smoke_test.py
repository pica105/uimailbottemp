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
import sys
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
from mailhub.bot_handlers import build_oauth_url  # noqa: E402


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
    msg4["From"] = "alice@example.com"
    msg4["Subject"] = "Meeting tomorrow"
    assert classify_yandex_message(msg4) == "important"
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

    await db.set_language(42, "ru")
    assert (await db.get_settings(42))["language"] == "ru"

    await db.update_settings(42, polling_interval_seconds=600, muted_categories=["promo"])
    settings_row = await db.get_settings(42)
    assert settings_row["polling_interval_seconds"] == 600
    assert settings_row["muted_categories"] == ["promo"]

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

    await db.mark_read(messages[0]["id"])
    fetched = await db.get_message(messages[0]["id"])
    assert fetched is not None and fetched["is_read"] == 1

    # OAuth state TTL
    await db.save_oauth_state("state-1", 42, "gmail")
    row = await db.get_oauth_state("state-1")
    assert row is not None and row["provider"] == "gmail"
    await db.delete_oauth_state("state-1")
    assert await db.get_oauth_state("state-1") is None

    await db.close()


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
    print("  ✓ gmail helpers")


if __name__ == "__main__":
    print("Running MailHub backend smoke tests...")
    test_crypto()
    test_classifier()
    test_database()
    test_init_data()
    test_oauth_urls()
    test_gmail_helpers()
    print("\nAll smoke tests passed ✅")
