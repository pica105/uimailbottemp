# MailHub 📬

Manage multiple mailboxes (Gmail, Yandex) right inside Telegram. The bot sends
smart notifications about new mail, and a native-feeling Mini App lets you
browse, read, and manage messages without leaving the chat.

**Warm, minimal, human.** The UI follows Telegram's native theme, overlaid with
warm amber accents, and speaks Russian and English.

---

## Architecture

```
┌─────────────┐   Telegram API   ┌────────────────────────────────────┐
│  Telegram   │ ◄──────────────► │  mailhub/  (single Python process) │
│  (bot +     │                  │  ├─ aiogram 3.x  — bot polling     │
│  Mini App)  │ ◄──────────────► │  ├─ aiohttp     — OAuth + REST API │
└─────────────┘   HTTPS/JSON     │  └─ SQLite      — mailhub.db       │
                                 └────────────────────────────────────┘
```

- **Backend** — one process, `python main.py`. No Docker, no Redis, no
  PostgreSQL, no Celery. Tokens are encrypted at rest with Fernet.
- **Frontend** — Next.js 16 Mini App (Vercel-ready), Tailwind v4, shadcn/ui.

```
mailhub/                  ← Python backend
├── main.py               # Entry point: bot + HTTP server + sync loop
├── config.py             # pydantic-settings, env validation
├── database.py           # aiosqlite: schema + queries
├── crypto.py             # Fernet encrypt/decrypt
├── bot_handlers.py       # aiogram handlers, keyboards, i18n, notifications
├── oauth_server.py       # aiohttp: OAuth callbacks + Mini App API
├── sync_engine.py        # background polling loop
├── sync_gmail.py         # Gmail REST incremental sync
├── sync_yandex.py        # Yandex IMAP + XOAUTH2 sync
├── classifier.py         # heuristic categorization
├── locales/              # ru.json, en.json
└── requirements.txt

mailhub-webapp/           ← Next.js 16 Mini App
├── app/                  # routes: /inbox, /message/[id], /settings
├── components/           # ui (shadcn), layout, mail, settings
├── hooks/                # useTelegram, useAuth, useMessages
├── lib/                  # api, telegram, i18n, utils
├── stores/               # Zustand app store
└── tests/                # Vitest (unit) + Playwright (e2e)
```

---

## Prerequisites

- **Python 3.12+** (tested with 3.13)
- **Node.js 20+** (tested with 24)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

---

## Backend setup

```bash
cd mailhub
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in values (see below)
python main.py
```

The process starts three things at once: the aiogram poller, the aiohttp
server (port 8080), and the mail sync loop. Ctrl+C shuts everything down
gracefully.

### `.env`

| Variable | Description |
|---|---|
| `BOT_TOKEN` | From @BotFather |
| `ENCRYPTION_KEY` | Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth (below) |
| `YANDEX_CLIENT_ID` / `YANDEX_CLIENT_SECRET` | Yandex OAuth (below) |
| `BASE_URL` | Public URL of this backend, e.g. `https://mailhub-backend.example.com` |
| `MINI_APP_URL` | Public URL of the Mini App, e.g. `https://your-app.vercel.app` |

---

## Frontend setup

```bash
cd mailhub-webapp
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL
npm run dev                         # http://localhost:3000
```

For production, deploy to Vercel:

```bash
npm run build
npx vercel deploy --prod
```

Set `NEXT_PUBLIC_API_URL` to the public backend URL in the Vercel project
settings.

---

## Google OAuth credentials

1. Go to https://console.cloud.google.com/apis/credentials
2. **Create Credentials → OAuth client ID → Web application**
3. Add the authorized redirect URI:
   `https://your-backend.example.com/oauth/gmail/callback`
4. Copy the Client ID and Secret into `.env`.
5. In **OAuth consent screen**, make sure the test mode includes your Google
   account, or publish the app.

---

## Yandex OAuth credentials

1. Go to https://oauth.yandex.ru/client/new
2. Choose **Web services**.
3. Add the redirect URI: `https://your-backend.example.com/oauth/yandex/callback`
4. Grant the scopes `login:email` and `mail:imap_full` (email address
   access for the `/info` endpoint, and full IMAP access to the mailbox).
   Note: the old `imap:full_mailbox` scope is no longer offered by Yandex.
5. Copy the Client ID and Secret into `.env`.

---

## BotFather setup

1. `/newbot` — create the bot, copy the token.
2. `/setdescription` — e.g. *"Manage Gmail and Yandex mailboxes inside Telegram."*
3. `/setcommands`:

```
start - Start / connect account
accounts - Manage accounts
settings - Open settings
help - Help
```

4. Set the Mini App menu button (the "Open in MailHub" button uses
   `MINI_APP_URL` from the backend env):

```
/menubutton — set the menu button URL to https://your-app.vercel.app
```

---

## Mini App API (used by the frontend)

All `/api/*` endpoints require the Telegram WebApp `initData` in the
`X-Telegram-Init-Data` header (validated with HMAC-SHA256).

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

---

## Backup

Everything lives in a single SQLite file. To back up, just copy it:

```bash
cp mailhub/mailhub.db mailhub.db.backup-$(date +%F)
```

---

## Testing

Backend smoke tests (crypto, DB, classifier, initData, OAuth URLs):

```bash
# from the project root
./.venv/bin/python scripts/smoke_test.py
```

Backend live API simulation (seeds a DB, starts the HTTP server, and
exercises every Mini App endpoint with valid initData):

```bash
# from the project root
./.venv/bin/python scripts/api_simulation.py
```

Frontend:

```bash
cd mailhub-webapp
npm run test          # Vitest unit tests
npm run typecheck
npm run lint
npx playwright install chromium   # one-time, needed for e2e
npm run test:e2e                  # Playwright (starts dev server)
```

---

## License

MIT — free to use, modify, and deploy.
