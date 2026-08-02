"""External end-to-end API test for the deployed MailHub backend.

Runs from the developer's PC against the PUBLIC domain
(https://uimail.synergyflow.ru) with a *valid* Telegram initData (HMAC-signed
with the real bot token) — exactly like the Telegram Mini App client does.

Covers: health, auth (401 without initData), accounts, settings read/write,
language persistence, automatic-only interval (ignored), messages, mark-read.

Usage (project root):
    ./.venv/bin/python scripts/external_api_test.py [--host URL]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
TELEGRAM_ID = 7496212856  # owner's Telegram id


def bot_token() -> str:
    env = ROOT / "mailhub" / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("BOT_TOKEN not found in mailhub/.env")


def build_init_data(token: str, telegram_id: int = TELEGRAM_ID) -> str:
    user = {"id": telegram_id, "first_name": "Gleb"}
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAHdF6AAAADdF6oG",
        "user": json.dumps(user),
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return f"{urlencode(fields)}&hash={signature}"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="https://uimail.synergyflow.ru")
    args = parser.parse_args()
    base = args.host.rstrip("/")

    token = bot_token()
    init_data = build_init_data(token)
    headers = {"X-Telegram-Init-Data": init_data}
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, note: str = "") -> None:
        checks.append((name, ok, note))
        print(f"  {'✓' if ok else '✗'} {name}" + (f" — {note}" if note else ""))

    async with aiohttp.ClientSession() as s:
        async def req(method: str, path: str, hdrs=None, body=None):
            kwargs = {"headers": hdrs}
            if body is not None:
                kwargs["json"] = body
            async with s.request(method, base + path, **kwargs) as r:
                try:
                    payload = await r.json()
                except Exception:
                    payload = {}
                return r.status, payload

        # 1. health (no auth)
        status, body = await req("GET", "/api/health")
        check("health", status == 200 and body.get("status") == "ok", str(status))

        # 2. no initData → 401
        status, _ = await req("GET", "/api/accounts")
        check("401 without initData", status == 401, str(status))

        # 3. accounts with valid initData
        status, body = await req("GET", "/api/accounts", headers)
        accounts = body.get("accounts", [])
        providers = {a["provider"] for a in accounts}
        check(
            "accounts (2, yandex+gmail)",
            status == 200 and len(accounts) == 2 and providers == {"yandex", "gmail"},
            f"{status}, {[(a['provider'], a['email']) for a in accounts]}",
        )

        # 4. settings GET
        status, body = await req("GET", "/api/settings", headers)
        st = body.get("settings", {})
        check(
            "settings GET",
            status == 200
            and st.get("language") in ("ru", "en")
            and st.get("polling_interval_seconds") == 300
            and len(st.get("accounts", [])) == 2,
            f"{status}, lang={st.get('language')}, interval={st.get('polling_interval_seconds')}",
        )

        # 5. PATCH language → ru (persists)
        status, body = await req(
            "PATCH", "/api/settings", headers, {"language": "ru"}
        )
        ok = status == 200 and body["settings"]["language"] == "ru"
        status2, body2 = await req("GET", "/api/settings", headers)
        ok = ok and status2 == 200 and body2["settings"]["language"] == "ru"
        check("PATCH language ru persists", ok, f"GET after -> {body2['settings']['language']}")

        # 6. PATCH polling_interval_seconds → ignored (automatic-only)
        status, body = await req(
            "PATCH", "/api/settings", headers, {"polling_interval_seconds": 60}
        )
        check(
            "interval ignored (stays 300)",
            status == 200 and body["settings"]["polling_interval_seconds"] == 300,
            f"{status}, interval={body['settings']['polling_interval_seconds']}",
        )

        # 7. messages for first account
        acc_id = accounts[0]["id"]
        status, body = await req("GET", f"/api/accounts/{acc_id}/messages", headers)
        msgs = body.get("messages", [])
        check(
            "messages list",
            status == 200 and len(msgs) > 0,
            f"{status}, {len(msgs)} messages",
        )

        # 8. message detail + mark read
        if msgs:
            mid = msgs[0]["id"]
            status, body = await req("GET", f"/api/messages/{mid}", headers)
            check("message detail", status == 200 and body["message"]["id"] == mid, str(status))
            status, body = await req("POST", f"/api/messages/{mid}/read", headers)
            check("mark read ok", status == 200 and body.get("ok") is True, str(status))
            status, body = await req("GET", f"/api/messages/{mid}", headers)
            check("mark read reflected", body["message"]["is_read"] is True, str(status))

        # 9. muted categories cleanup
        status, body = await req("PATCH", "/api/settings", headers, {"muted_categories": []})
        check(
            "PATCH muted_categories",
            status == 200 and body["settings"]["muted_categories"] == [],
            str(status),
        )

    print("\n=== EXTERNAL TEST SUMMARY ===")
    all_ok = all(ok for _, ok, _ in checks)
    print("ALL CHECKS PASSED ✅" if all_ok else "SOME CHECKS FAILED ❌")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
