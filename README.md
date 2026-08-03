# MailHub

Read and manage Gmail and Yandex mailboxes from inside Telegram. The bot delivers new-mail notifications straight to the chat; the Mini App is a full inbox: list, categories, message view, mark-as-read — no extra apps.

## Features

- **OAuth connect** for Gmail and Yandex, one tap in the chat
- **New-mail notifications** to Telegram; Promo and Spam are always suppressed, with optional muting for other categories
- **Mini App** (inside Telegram): inbox, category tabs (All / Important / Social / Other), message detail with body and Load more pagination
- **Mark-as-read** that syncs back to the real mailbox (Gmail `modify`, Yandex `\Seen`)
- **Elastic polling** per account (fully automatic): 10 s right after new mail, grows with idle time, caps at 5 min. A new message resets it to 10 s
- **RU / EN**, native Telegram theme (light and dark)

## How it works

One Python process runs everything: the aiogram bot (long polling), the aiohttp server (OAuth callbacks + REST API), and the sync loop. Tokens are encrypted at rest with Fernet. State lives in a single SQLite file. No Docker, no Redis, no PostgreSQL, no Celery.

```
┌─────────────┐  Telegram API   ┌─────────────────────────────────────┐
│  Telegram   │ ◄─────────────► │  mailhub/ — single asyncio process   │
│  bot +      │                 │  ├─ aiogram 3.x — bot + notifications│
│  Mini App   │ ◄─────────────► │  ├─ aiohttp    — OAuth + REST API    │
└─────────────┘  HTTPS/JSON     │  └─ SQLite     — mailhub.db          │
                                └─────────────────────────────────────┘
```

Sync details:

- **Gmail** — REST only. Bootstrap: latest 50 messages plus up to 50 latest unread messages (`is:unread in:inbox`). Then paginated `users.history` incremental sync; expired history IDs trigger a fresh bootstrap. Mark-as-read removes the `UNREAD` label (`messages.modify`).
- **Yandex** — IMAP over XOAUTH2 (`aioimaplib`, `imap.yandex.ru:993`). UID-based incremental search plus one-time unread backfill, newest-first batches of 50. Mark-as-read issues `STORE +FLAGS (\Seen)`.
- **Elastic interval** — `max(10 s, min(5 min, idle_seconds / 10))`, fully automatic per account (not user-configurable). Fresh mail → 10 s. Silent mailbox → grows toward the 5 min cap. Errors back off exponentially (`2^n × 60 s`, capped at 1 h).

Frontend is a Next.js Mini App served from the same domain, authenticated by Telegram WebApp `initData` (HMAC-SHA256) on every API call.

## Stack

| Part | Tech |
|---|---|
| Backend | Python 3.12, aiogram 3, aiohttp, aiosqlite, aioimaplib, cryptography (Fernet), pydantic-settings |
| Frontend | Next.js 16, React 19, Tailwind v4, shadcn/ui (Radix), TanStack Query v5, Zustand, Zod |
| Tests | `scripts/smoke_test.py` + `scripts/api_simulation.py` (backend), Vitest + Playwright (frontend) |

## Quickstart

### Prerequisites

- Python 3.12+
- Node.js 20+
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- Google and Yandex OAuth apps (see below)

### Backend

```bash
cd mailhub
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # fill in the values below
python main.py
```

The process starts the bot poller, the HTTP server (`PORT`, default 8080), and the sync loop. Ctrl+C shuts everything down gracefully.

`.env`:

| Variable | Description |
|---|---|
| `BOT_TOKEN` | From @BotFather |
| `ENCRYPTION_KEY` | Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth app |
| `YANDEX_CLIENT_ID` / `YANDEX_CLIENT_SECRET` | Yandex OAuth app |
| `BASE_URL` | Public URL of this backend, e.g. `https://mailhub-backend.example.com` — used to build OAuth redirect URIs |
| `MINI_APP_URL` | Public URL of the Mini App (the "Open in MailHub" button) |
| `DB_PATH` | SQLite file location (default `./mailhub.db`) |

### Frontend

```bash
cd mailhub-webapp
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL to the backend URL
npm run dev                        # http://localhost:3000
```

Production build: `npm run build && npm start`.

### Google OAuth

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → Create credentials → OAuth client ID → Web application.
2. Authorized redirect URI: `https://your-backend.example.com/oauth/gmail/callback`.
3. Copy Client ID / Secret into `.env`.
4. Add your Google account as a test user (or publish the app).
5. Scope is requested automatically: `gmail.modify` (read + mark-as-read).

### Yandex OAuth

1. [Yandex OAuth](https://oauth.yandex.ru/client/new) → Web services.
2. Redirect URI: `https://your-backend.example.com/oauth/yandex/callback`.
3. Scopes: `login:email` and `mail:imap_full`.
4. Copy Client ID / Secret into `.env`.

### BotFather

```
/newbot          — create the bot, copy the token
/setcommands     — start - Start / connect account
                   accounts - Manage accounts
                   settings - Open settings
                   help - Help
/menubutton      — set the menu button URL to the Mini App (MINI_APP_URL)
```

## Mini App API

Every `/api/*` route validates the Telegram WebApp `initData` passed in the `X-Telegram-Init-Data` header.

```
GET    /api/health
GET    /api/accounts
DELETE /api/accounts/{id}
GET    /api/accounts/{id}/messages?category=&limit=&offset=
GET    /api/messages/{id}
POST   /api/messages/{id}/read
GET    /api/settings
PATCH  /api/settings

GET    /oauth/gmail/callback?code=&state=
GET    /oauth/yandex/callback?code=&state=
```

## Tests

```bash
# backend — from the project root
./.venv/bin/python scripts/smoke_test.py        # crypto, DB, classifier, initData, OAuth URLs, parsers
./.venv/bin/python scripts/api_simulation.py    # live HTTP + every endpoint

# frontend — from mailhub-webapp
npm run test          # Vitest unit tests
npm run typecheck
npm run lint
npx playwright install chromium   # once, for e2e
npm run test:e2e
```

## Deployment (self-hosted)

The production setup is two systemd services plus nginx:

- `mailhub` — `python -m mailhub.main` on `127.0.0.1:8000`
- `mailhub-web` — `next start -p 3001` (built with `npm run build`)
- nginx: `/` → 3001, `/api/` and `/oauth/` → 8000, TLS via certbot

See `docs/01-backend.md` for the full operational details.

## Repository layout

```
mailhub/                  ← Python backend
├── main.py               # entry point: bot + HTTP server + sync loop
├── config.py             # pydantic-settings, env validation
├── database.py           # aiosqlite: schema + queries
├── crypto.py             # Fernet encrypt/decrypt
├── bot_handlers.py       # aiogram handlers, keyboards, i18n, notifications
├── oauth_server.py       # aiohttp: OAuth callbacks + Mini App API
├── sync_engine.py        # background polling loop + elastic interval
├── sync_gmail.py         # Gmail REST incremental sync
├── sync_yandex.py        # Yandex IMAP + XOAUTH2 sync
├── mark_read.py          # provider-side mark-as-read (best-effort)
├── classifier.py         # heuristic categorization
└── locales/              # ru.json, en.json

mailhub-webapp/           ← Next.js 16 Mini App
├── app/                  # routes: /inbox, /message/[id], /settings
├── components/           # ui (shadcn), layout, mail, settings
├── hooks/                # useTelegram, useAuth, useMessages
├── lib/                  # api, telegram, i18n, utils
└── stores/               # Zustand app store
```

## License

MIT — free to use, modify, and deploy.
