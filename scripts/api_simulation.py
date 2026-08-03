"""Realistic user simulation against the live aiohttp API.

Seeds a SQLite DB with a user, two accounts, and a few messages, starts the
actual aiohttp app from mailhub.oauth_server, and exercises every endpoint
the Mini App calls — with *valid* initData (HMAC-signed with the test bot
token), exactly like the real Telegram client would send.

Run from project root:
    BOT_TOKEN=123456:test-token-abc ENCRYPTION_KEY=<fernet key> \
        ./.venv/bin/python scripts/api_simulation.py
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
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("BOT_TOKEN", "123456:test-token-abc")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import aiohttp  # noqa: E402

from mailhub.config import settings  # noqa: E402
from mailhub.crypto import encrypt  # noqa: E402
from mailhub.database import Database  # noqa: E402
from mailhub.oauth_server import create_app  # noqa: E402

TELEGRAM_ID = 424242
DB_PATH = "/tmp/mailhub_sim.db"


def build_init_data(telegram_id: int = TELEGRAM_ID) -> str:
    """Build initData signed with the test token (mirrors the real client)."""
    user = {"id": telegram_id, "first_name": "Alice", "language_code": "ru"}
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAHdF6AAAADdF6oG",
        "user": json.dumps(user),
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    # Fully URL-encode each field exactly like the real Telegram client.
    params = urlencode(fields)
    return f"{params}&hash={signature}"


async def seed(db: Database) -> None:
    await db.connect()
    await db.get_or_create_user(
        TELEGRAM_ID, username="alice", first_name="Alice", last_name="A"
    )
    await db.set_language(TELEGRAM_ID, "ru")
    await db.update_settings(TELEGRAM_ID, muted_categories=["promo"])
    gmail = await db.add_account(
        TELEGRAM_ID, "gmail", "alice@gmail.com",
        encrypt("fake-access"), encrypt("fake-refresh"), int(time.time()) + 3600,
    )
    yandex = await db.add_account(
        TELEGRAM_ID, "yandex", "alice@yandex.ru",
        encrypt("fake-access"), encrypt("fake-refresh"), int(time.time()) + 3600,
    )
    msgs = [
        (gmail["id"], "gmail-1", "John Doe", "john@example.com", "Meeting tomorrow",
         "Hey, are we still on for the meeting?", "important", 1000),
        (gmail["id"], "gmail-2", "Spotify", "no-reply@spotify.com", "Your weekly digest",
         "Here's what you listened to this week.", "promo", 900),
        (yandex["id"], "yandex-1", "Банк", "info@bank.ru", "Код подтверждения",
         "Ваш код: 1234", "important", 800),
    ]
    for account_id, pid, name, email, subj, snippet, cat, recv in msgs:
        await db.upsert_message(
            account_id, pid, sender_name=name, sender_email=email,
            subject=subj, snippet=snippet, body_text=snippet,
            category=cat, received_at=recv,
        )
    for index in range(22):
        await db.upsert_message(
            gmail["id"], f"gmail-important-{index}", sender_name="Colleague",
            sender_email="colleague@example.com", subject=f"Recent update {index}",
            snippet="Fresh message", body_text="Fresh message",
            category="important", received_at=2000 + index,
        )


async def main() -> None:
    Path(DB_PATH).unlink(missing_ok=True)

    db = Database(DB_PATH)
    await seed(db)

    app = create_app(db, bot=None)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 18080)
    await site.start()
    print("Server listening on http://127.0.0.1:18080")

    init_data = build_init_data()
    base = "http://127.0.0.1:18080"
    headers = {"X-Telegram-Init-Data": init_data}
    checks = []

    async with aiohttp.ClientSession() as s:
        async def get(path, hdrs=None):
            async with s.get(base + path, headers=hdrs) as r:
                return r.status, await r.json()

        async def post(path, body=None, hdrs=None):
            async with s.post(base + path, json=body, headers=hdrs) as r:
                return r.status, await r.json()

        async def patch(path, body=None, hdrs=None):
            async with s.patch(base + path, json=body, headers=hdrs) as r:
                return r.status, await r.json()

        async def delete(path, hdrs=None):
            async with s.delete(base + path, headers=hdrs) as r:
                return r.status, await r.json()

        # 1. health (no auth required)
        status, body = await get("/api/health")
        checks.append(("health", status == 200 and body["status"] == "ok", status, body))

        # 2. accounts list
        status, body = await get("/api/accounts", headers)
        ok = status == 200 and len(body["accounts"]) == 2
        checks.append(("accounts", ok, status, body))

        # 3. messages with category filter
        gmail_id = body["accounts"][0]["id"]
        status, body = await get(f"/api/accounts/{gmail_id}/messages?category=important", headers)
        ok = (
            status == 200
            and len(body["messages"]) == 20
            and body["messages"][0]["subject"] == "Recent update 21"
            and body["has_more"] is True
        )
        checks.append(("messages(important) first page", ok, status, body))

        # 4. all messages
        status, body = await get(f"/api/accounts/{gmail_id}/messages", headers)
        ok = (
            status == 200
            and len(body["messages"]) == 20
            and body["has_more"] is True
            and all(m["category"] not in {"promo", "spam"} for m in body["messages"])
        )
        checks.append(("messages(all) hides promo/spam", ok, status, body))

        status, body = await get(
            f"/api/accounts/{gmail_id}/messages?category=important&limit=20&offset=20",
            headers,
        )
        ok = (
            status == 200
            and len(body["messages"]) == 3
            and body["has_more"] is False
            and len({m["id"] for m in body["messages"]}) == 3
        )
        checks.append(("messages(important) second page", ok, status, body))

        # 5. single message
        msg_id = body["messages"][0]["id"]
        status, body = await get(f"/api/messages/{msg_id}", headers)
        ok = status == 200 and body["message"]["id"] == msg_id and body["message"]["body_text"]
        checks.append(("message detail", ok, status, body))

        # 6. mark read
        status, body = await post(f"/api/messages/{msg_id}/read", hdrs=headers)
        checks.append(("mark read", status == 200 and body.get("ok") is True, status, body))
        status, body = await get(f"/api/messages/{msg_id}", headers)
        checks.append(("read reflected", body["message"]["is_read"] is True, status, body))

        # 7. settings (must include accounts + dynamic categories, no interval)
        status, body = await get("/api/settings", headers)
        ok = (
            status == 200
            and body["settings"]["language"] == "ru"
            and "polling_interval_seconds" not in body["settings"]
            and "promo" in body["settings"]["muted_categories"]
            and body["settings"]["categories"] == ["important", "social", "other"]
            and len(body["settings"]["accounts"]) == 2
        )
        checks.append(("settings", ok, status, body))

        # 8. PATCH settings — interval is ignored (fixed 10s); response must
        #    include accounts (contract fix)
        status, body = await patch(
            "/api/settings",
            {"language": "en", "polling_interval_seconds": 60, "muted_categories": ["spam"]},
            headers,
        )
        ok = (
            status == 200
            and body["settings"]["language"] == "en"
            and "polling_interval_seconds" not in body["settings"]
            and body["settings"]["muted_categories"] == ["spam"]
            and len(body["settings"]["accounts"]) == 2
        )
        checks.append(("PATCH settings (interval ignored, accounts present)", ok, status, body))

        # 8b. OAuth start from the Mini App returns a signed auth URL
        status, body = await post(
            "/api/oauth/start", {"provider": "gmail"}, headers
        )
        ok = status == 200 and "auth_url" in body and "accounts.google.com" in body["auth_url"]
        checks.append(("oauth/start returns auth url", ok, status, body))
        status, body = await post(
            "/api/oauth/start", {"provider": "dropbox"}, headers
        )
        checks.append(("oauth/start rejects bad provider", status == 400, status, body))

        # 9. unauthorized without initData
        status, body = await get("/api/accounts")
        checks.append(("401 without initData", status == 401, status, body))

        # 10. tampered initData rejected
        tampered = build_init_data(TELEGRAM_ID).replace("Alice", "Eve")
        status, body = await get("/api/accounts", {"X-Telegram-Init-Data": tampered})
        checks.append(("401 tampered initData", status == 401, status, body))

        # 11. ownership: other user cannot read someone else's message
        other = build_init_data(999)
        status, body = await get(f"/api/messages/{msg_id}", {"X-Telegram-Init-Data": other})
        checks.append(("ownership enforced", status == 404, status, body))

        # 12. invalid pagination
        status, body = await get(f"/api/accounts/{gmail_id}/messages?limit=abc", headers)
        checks.append(("invalid pagination -> 400", status == 400, status, body))

        # 13. DELETE account
        status, body = await delete(f"/api/accounts/{gmail_id}", headers)
        checks.append(("delete account", status == 200 and body.get("ok") is True, status, body))
        status, body = await get("/api/accounts", headers)
        checks.append(("deleted reflected", status == 200 and len(body["accounts"]) == 1, status, body))

    await runner.cleanup()
    await db.close()

    print("\n=== SIMULATION RESULTS ===")
    all_ok = True
    for name, ok, status, body in checks:
        mark = "✓" if ok else "✗"
        if not ok:
            all_ok = False
        print(f"  {mark} {name} (HTTP {status})")
    print("\nALL CHECKS PASSED ✅" if all_ok else "\nSOME CHECKS FAILED ❌")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
