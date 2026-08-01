# MailHub Bot — Production-Ready Development Prompt

> **CRITICAL WORKFLOW DIRECTIVE**
> 
> Work using a multi-agent system. First, break the overall task down into macro tasks and micro tasks (each macro task should consist of 10–20 micro tasks).
> 
> For each micro task, follow this workflow:
> 
> 1. Launch 4 implementation agents that independently solve the micro task. Each agent should:
>    - write the required code for its approach;
>    - explain its reasoning;
>    - analyze potential problems;
>    - propose ways to solve those problems.
> 
> 2. Launch 2 evaluation agents that review the outputs of the 4 implementation agents, select the strongest solution, and improve it if necessary.
> 
> 3. Launch 1 final integration agent that reviews the selected solution, chooses the single best version, and refines it further if needed.
> 
> 4. Test the resulting code for the micro task.
> 
> 5. Perform a code review.
> 
> 6. Simulate real user behavior and interactions to validate the implementation under realistic usage scenarios.
> 
> 7. If any bugs, inconsistencies, or failures are found, restart the entire workflow for that micro task from the beginning (starting with the 4 implementation agents). This time, provide all agents with:
>    - execution logs;
>    - error messages;
>    - explanations of the detected issues;
>    - the code review report;
>    - any additional debugging information gathered during testing.
> 
> Repeat this iterative process until the micro task passes testing, review, and user simulation without issues.

---

## 1. Role Definition

You are a Senior Python Developer and Frontend Architect with deep expertise in:
- Production-grade Telegram Bot development (aiogram 3.x, WebApp SDK)
- Lightweight async Python architecture (single-process, asyncio)
- OAuth2 integrations (Gmail API, Yandex OAuth)
- Modern React/Next.js frontend (App Router, TypeScript)

Your output must be **production-ready, clean, simple code following 2026 best practices**. No over-engineering. No unnecessary abstractions. Every function must be fully implemented, typed, and handle edge cases.

---

## 2. Tech Stack

### 2.1 Backend (Single Python Process)
- **Python**: 3.12+
- **Bot Framework**: aiogram 3.x (async polling)
- **HTTP Server**: `aiohttp` (built-in, same process as bot — handles OAuth callbacks and Mini App API)
- **Database**: SQLite with `aiosqlite` (async, file-based, zero external services)
- **Token Encryption**: `cryptography` (Fernet) for OAuth tokens at rest
- **Mail Protocols**:
  - Gmail: `google-api-python-client` + `google-auth-oauthlib`
  - Yandex: `aioimaplib` (IMAP + XOAUTH2)
  - MIME Parsing: Python built-in `email` module
- **Configuration**: `pydantic-settings` with env validation
- **Launch**: Single file `python main.py` starts everything

### 2.2 Frontend (Telegram Mini App)
- **Framework**: Next.js 16 (App Router, strict TypeScript)
- **React**: 19
- **Language**: TypeScript 5.x (strict mode)
- **Styling**: Tailwind CSS v4
- **UI Components**: shadcn/ui (Radix UI primitives)
- **State Management**: Zustand
- **Server State**: TanStack Query
- **Forms**: React Hook Form + Zod
- **Tables**: TanStack Table v8
- **Animations**: Motion
- **Icons**: Lucide React
- **Date/Time**: date-fns
- **Charts**: Recharts (if needed)
- **Code Quality**: ESLint + Prettier
- **Testing**: Vitest + Playwright
- **Deployment**: Vercel

### 2.3 Infrastructure
- **Backend**: Single Python process running on any VPS or even locally. Just `python main.py`. No Docker, no systemd, no Nginx required (but can be put behind Nginx if desired — not mandatory).
- **Frontend**: Vercel (automatic HTTPS)
- **Database**: Single SQLite file (`mailhub.db`) in project folder
- **No Redis, No PostgreSQL, No RabbitMQ, No Celery, No Docker, No separate worker processes.**

---

## 3. Application Logic & Architecture

### 3.1 High-Level Flow
```
User sends /start → Bot (aiogram, same process)
    ↓
Language selection (inline keyboard: 🇷🇺 Русский / 🇬🇧 English)
    ↓
Onboarding → "Connect Account" button
    ↓
Provider selection (Gmail / Yandex) → OAuth URL
    ↓
User authorizes in browser → aiohttp server /oauth/{provider}/callback
    ↓
Tokens encrypted → Saved to SQLite
    ↓
Bot sends confirmation message
    ↓
Background asyncio.Task polls mail every N minutes
    ↓
New email → SQLite → Bot notification with "Open in MailHub" button
```

### 3.2 Backend Architecture (Single Process, Flat Structure)
Keep it simple. All backend code lives in one folder with ~8 files:

```
mailhub/
├── main.py              # Entry point: starts bot + aiohttp server + sync loop
├── config.py            # pydantic-settings, env vars
├── database.py          # aiosqlite: connection, schema, simple queries
├── crypto.py            # Fernet encrypt/decrypt
├── bot_handlers.py      # All aiogram handlers, keyboards, middlewares
├── oauth_server.py      # aiohttp routes: OAuth callbacks + Mini App API
├── sync_engine.py       # Background mail polling loop
├── classifier.py        # Heuristic email categorization
├── locales/
│   ├── ru.json          # Russian translations
│   └── en.json          # English translations
├── requirements.txt
└── .env.example
```

**`main.py`** is the heart. It launches three concurrent coroutines:
1. `start_bot()` — aiogram polling
2. `start_server()` — aiohttp on port 8080 (OAuth + API)
3. `start_sync()` — background mail sync loop

Use `asyncio.gather()` with graceful shutdown on Ctrl+C.

### 3.3 Frontend Architecture (Next.js 16 App Router)
```
mailhub-webapp/
├── app/
│   ├── layout.tsx       # Root: Telegram WebApp SDK init, theme provider
│   ├── page.tsx         # Redirect to /inbox
│   ├── (app)/
│   │   ├── layout.tsx   # App shell: header, account switcher
│   │   ├── inbox/
│   │   │   └── page.tsx # Message list with category tabs
│   │   ├── message/
│   │   │   └── [id]/
│   │   │       └── page.tsx
│   │   └── settings/
│   │       └── page.tsx
├── components/
│   ├── ui/              # shadcn/ui components
│   ├── layout/          # Header, AccountSwitcher, CategoryTabs
│   ├── mail/            # MessageList, MessageRow, MessageDetail, EmptyState
│   └── settings/        # LanguageSelector, PollingInterval, MutedCategories
├── hooks/
│   ├── useTelegram.ts   # WebApp SDK wrapper
│   ├── useAuth.ts       # initData handling
│   └── useMessages.ts   # TanStack Query hooks
├── lib/
│   ├── api.ts           # Typed fetch client
│   ├── telegram.ts      # initData parsing, HMAC validation
│   └── utils.ts         # cn(), formatters
├── stores/
│   └── appStore.ts      # Zustand store
├── types/
│   └── index.ts         # TypeScript interfaces
├── tests/
│   ├── vitest/
│   └── e2e/
└── .env.local.example
```

---

## 4. Functional Requirements & Details

### 4.1 Localization (i18n) — CRITICAL
The bot MUST support **Russian and English**.

**Implementation**:
- Store `language_code` in `users` table (`ru` or `en`).
- On `/start`, if no language is set, show inline keyboard:
  - `🇷🇺 Русский` (callback_data: `lang:ru`)
  - `🇬🇧 English` (callback_data: `lang:en`)
- All bot messages, buttons, and command descriptions are localized via JSON dictionaries (`locales/ru.json`, `locales/en.json`).
- The Mini App reads language from backend and renders all UI text in the selected language. Use a lightweight translation hook (custom, based on Zustand state).
- **Language can be changed anytime** in Mini App Settings. Updates DB and UI immediately without reload.

### 4.2 Onboarding & OAuth Flow

**Step 1 — Start**:
```
/start → "Welcome to MailHub! 👋

Manage multiple mailboxes inside Telegram."
[Connect Account] [Settings] [Help]
```

**Step 2 — Provider Selection**:
```
[📧 Gmail] [📧 Yandex Mail]
```

**Step 3 — OAuth**:
- Generate state-protected OAuth URL (store state in temporary dict with TTL or SQLite)
- Gmail: Google OAuth2 (scopes: `gmail.readonly`, `gmail.labels`)
- Yandex: Yandex OAuth (scopes: `login:email`, `mail:imap_full`)
- Callback handled by aiohttp: `/oauth/gmail/callback` and `/oauth/yandex/callback`

**Step 4 — Post-Auth**:
- Exchange code for tokens
- Encrypt with Fernet
- Save to `mail_accounts` table
- Bot sends: "✅ Account `user@gmail.com` connected!"

### 4.3 Multi-Account Management
- Unlimited accounts per user
- Each account: `id`, `provider`, `email`, `is_active`
- **Active account**: Selected in Mini App header dropdown. Stored in Zustand.
- **Switching**: Inline keyboard in bot OR dropdown in Mini App
- **Disconnect**: "Unlink" button → Confirmation → DELETE from DB, tokens wiped

### 4.4 Mail Synchronization Engine

**Simple background loop inside the same process:**
```python
async def sync_loop():
    while True:
        accounts = await db.get_active_accounts()
        for account in accounts:
            try:
                if account.next_sync_at <= now:
                    await sync_account(account)
                    await db.update_next_sync(account.id, interval)
            except Exception as e:
                logger.error(f"Sync failed for {account.email}: {e}")
                await db.increment_error(account.id)
        await asyncio.sleep(60)  # Base loop every 60 seconds
```

**Per-User Polling Interval**:
- Stored in `users.polling_interval_seconds` (default: 300, min: 60, max: 1800)
- Engine checks `next_sync_at` per account

**Gmail Sync (Incremental)**:
- First sync: `users.messages.list(maxResults=50)`, store `historyId`
- Subsequent: `users.history.list` with `startHistoryId`
- Map Gmail categories:
  - `CATEGORY_PERSONAL` → `important`
  - `CATEGORY_PROMOTIONS` → `promo`
  - `CATEGORY_SOCIAL` → `promo`
  - `CATEGORY_UPDATES` → `other`
  - `CATEGORY_FORUMS` → `other`
  - No category → `important`

**Yandex Sync (IMAP + XOAUTH2)**:
- Connect to `imap.yandex.ru:993` via `aioimaplib`
- Track last UID, fetch `UNSEEN` or new UIDs
- Parse headers with Python `email` module

**Categorization Heuristics (Yandex)**:
```python
def classify_yandex_message(headers):
    if "List-Unsubscribe" in headers:
        return "promo"
    if any(domain in headers.get("From", "") for domain in SPAM_DOMAINS):
        return "spam"
    if any(keyword in headers.get("Subject", "").lower() for keyword in SPAM_KEYWORDS):
        return "spam"
    return "important"
```
- Keep a small domain/keyword blacklist in `config.py`.

### 4.5 Notifications
When new messages are detected:
1. Check `muted_categories` (JSON array in user settings, e.g., `["promo", "spam"]`)
2. If category not muted:
   - Send Telegram message:
   ```
   📬 New email — Important

   **From:** John Doe
   **Subject:** Meeting tomorrow

   _Snippet: "Hey, are we still on for the meeting..."_

   [Open in MailHub] [Mark as Read]
   ```
3. Set `messages_cache.notified_at = NOW()`
4. "Open in MailHub" = `web_app` button linking to `https://your-app.vercel.app/message/{id}`

### 4.6 Mini App Screens

**Screen 1 — Inbox (`/inbox`)**:
- Header: Account switcher (dropdown with provider icons)
- Tabs: All | Important | Promo | Spam (shadcn/ui Tabs, animated underline)
- Message list:
  - Colored circle avatar (first letter of sender, deterministic color from email hash)
  - Sender name bold if unread
  - Subject second line, truncated
  - Relative time (date-fns, localized)
  - Category badge (small pill)
  - Tap row → `/message/{id}`
- Pull-to-refresh (TanStack Query refetch)
- Empty state: large Lucide `Inbox` icon, warm friendly text

**Screen 2 — Message Detail (`/message/{id}`)**:
- Header: Back button (Telegram WebApp BackButton API)
- Card:
  - Avatar + sender name + email
  - Date (localized)
  - Subject
  - Body text (plain text, `whitespace-pre-wrap`, sanitize HTML if any)
  - Category badge
- Bottom action: [Mark as Read] if unread

**Screen 3 — Settings (`/settings`)**:
- Language: Russian / English selector (immediate effect)
- Polling interval: Slider/select (1, 3, 5, 10, 15, 30 min)
- Muted categories: Toggle switches (Promo, Spam, Other)
- Connected accounts: List with provider icon, email, "Unlink" button (shadcn AlertDialog for confirmation)
- All forms: React Hook Form + Zod

### 4.7 Telegram Theme Integration
- Read `window.Telegram.WebApp.themeParams` on launch
- Apply as CSS variables (`--tg-bg`, `--tg-text`, etc.)
- Use Tailwind with these variables
- Support light/dark seamlessly
- The "warm modern" design blends with Telegram theme, adding subtle grid overlay and soft gradients on top

---

## 5. Visual Design & UX Specification

### 5.1 Design Philosophy
**Modern Minimalism with Warmth**. No generic AI look:
- Warm, earthy tones (amber, peach, soft coral)
- Purposeful whitespace
- Consistent radius: `rounded-xl` for cards, `rounded-lg` for buttons
- Subtle shadows instead of harsh borders

### 5.2 Color Palette
Base on Telegram theme params, overlay warm accents:
- **Primary**: Warm amber `#F59E0B` → `#D97706`
- **Secondary**: Soft coral `#FCA5A5` → `#FECACA`
- **Background**:
  - Base: Telegram `bg_color`
  - Gradient overlay: `from-orange-50/30 to-amber-50/10` (light), `from-slate-800/50 to-slate-900/20` (dark)
  - Grid: CSS dot/line grid at ~2% opacity, fading at bottom
- **Text**: Telegram `text_color`, `hint_color`
- **Badges**:
  - Important: red tones
  - Promo: blue tones
  - Spam: gray tones
  - Other: amber tones

### 5.3 Typography
- System font stack (no custom fonts)
- Sender: `font-semibold text-base`
- Subject: `font-medium text-sm text-muted-foreground`
- Snippet: `text-sm text-hint`
- Time: `text-xs text-hint tabular-nums`

### 5.4 Animations (Motion)
- Page transitions: fade + slight upward slide (`duration: 0.25s`)
- List items: staggered entrance (`staggerChildren: 0.03`)
- Tab switching: sliding underline/pill (`layout` prop)
- Button taps: `whileTap={{ scale: 0.97 }}`
- Loading: shimmer skeletons

### 5.5 Background Pattern
Subtle fixed grid behind content:
```css
.grid-bg {
  background-image: 
    linear-gradient(to right, var(--tg-hint-color) 1px, transparent 1px),
    linear-gradient(to bottom, var(--tg-hint-color) 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.03;
  mask-image: linear-gradient(to bottom, black 40%, transparent 100%);
}
```

---

## 6. Database Schema (SQLite)

Use `aiosqlite`. Run schema creation on startup in `main.py`.

### 6.1 Tables

**`users`**
```sql
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('ru', 'en')),
    polling_interval_seconds INTEGER NOT NULL DEFAULT 300 CHECK(polling_interval_seconds BETWEEN 60 AND 1800),
    muted_categories TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**`mail_accounts`**
```sql
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, email)
);
CREATE INDEX IF NOT EXISTS idx_accounts_user ON mail_accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_accounts_next_sync ON mail_accounts(next_sync_at);
```

**`messages_cache`**
```sql
CREATE TABLE IF NOT EXISTS messages_cache (
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
CREATE INDEX IF NOT EXISTS idx_messages_account ON messages_cache(account_id);
CREATE INDEX IF NOT EXISTS idx_messages_category ON messages_cache(category);
CREATE INDEX IF NOT EXISTS idx_messages_received ON messages_cache(received_at);
```

### 6.2 Data Access
- All DB operations async via `aiosqlite`
- Simple functions in `database.py`: `get_user()`, `add_account()`, `get_messages()`, etc.
- Handle `sqlite3.IntegrityError` gracefully

---

## 7. Backend Implementation Details

### 7.1 Security
- **Token Encryption**: `cryptography.fernet.Fernet` with key from `ENCRYPTION_KEY` env var. Encrypt before DB, decrypt in memory only during API calls.
- **initData Validation**: In aiohttp middleware/dependency, parse `initData` from header. Compute HMAC-SHA256 with `HMAC_SHA256(bot_token, "WebAppData")` as key. Reject if mismatch or auth_date > 24h old.
- **HTTPS**: Use Vercel for frontend (HTTPS by default). Backend can run behind Cloudflare Tunnel or simple Nginx if on VPS — but keep backend code HTTP-agnostic.
- **Secrets**: All in `.env`. Never log tokens. Partial log emails: `j***@example.com`.
- **OAuth State**: Random state string, store in temporary SQLite table or in-memory dict with 10-minute TTL. Verify on callback.

### 7.2 Error Handling & Resilience
- **Per-account isolation**: One account failure must not crash others.
- **Token refresh**: On 401 from Gmail, try refresh once. If fails, deactivate account and notify user.
- **Retry backoff**: `sync_error_count` → next retry after `min(2^count * 60, 3600)` seconds.
- **Graceful shutdown**: `main.py` catches SIGINT/SIGTERM, cancels tasks gracefully.

### 7.3 API Endpoints (aiohttp)
All Mini App endpoints require initData in `X-Telegram-Init-Data` header.

```
GET  /api/health
GET  /api/accounts              # List accounts
DELETE /api/accounts/{id}       # Unlink
GET  /api/accounts/{id}/messages?category=&limit=&offset=
GET  /api/messages/{id}
POST /api/messages/{id}/read
GET  /api/settings
PATCH /api/settings

# OAuth (browser flow, no initData)
GET /oauth/gmail/callback?code=&state=
GET /oauth/yandex/callback?code=&state=
```

### 7.4 Bot Commands
```
/start     — Welcome + language selection
/accounts  — Manage accounts
/settings  — Open settings
/help      — Help info
```

---

## 8. Frontend Implementation Details

### 8.1 Telegram WebApp SDK
Client-side `TelegramProvider`:
- `WebApp.ready()` on mount
- `WebApp.expand()` for full viewport
- Listen `themeChanged`, update CSS vars
- Manage `BackButton` based on route
- `HapticFeedback.impactOccurred('light')` on taps

### 8.2 API Client
- Native `fetch` with typed wrapper
- Send `X-Telegram-Init-Data` header
- Zod-parse responses
- Handle 401 with "Reopen from Telegram" message

### 8.3 State Management (Zustand)
```typescript
interface AppState {
  language: 'ru' | 'en';
  activeAccountId: number | null;
  activeCategory: 'all' | 'important' | 'promo' | 'spam';
  setLanguage: (lang: 'ru' | 'en') => void;
  setActiveAccount: (id: number) => void;
  setActiveCategory: (cat: AppState['activeCategory']) => void;
}
```

### 8.4 Forms
Settings schema:
```typescript
const settingsSchema = z.object({
  language: z.enum(['ru', 'en']),
  pollingInterval: z.number().min(60).max(1800),
  mutedCategories: z.array(z.enum(['promo', 'spam', 'other'])),
});
```

### 8.5 Testing
- **Vitest**: Utilities, store logic, formatters
- **Playwright**: Inbox load, tab switch, message open, settings save

---

## 9. Out of Scope (v2)

Do NOT implement now, but keep code extensible:
- Sending/replying/forwarding emails
- Attachments
- Outlook, Mail.ru, iCloud
- AI summarization
- Webhook/IMAP IDLE push
- Monetization
- Full-text search
- HTML email rendering (MVP: plain text only)

---

## 10. Deliverables

### 10.1 Backend (`mailhub/`)
- **`main.py`**: Single entry point. Starts aiogram bot, aiohttp server, and sync loop concurrently via `asyncio.gather()`. Handles graceful shutdown.
- **`config.py`**: Pydantic settings. All env vars validated at startup.
- **`database.py`**: aiosqlite wrapper. Schema creation on startup. Simple async functions: `get_user()`, `create_user()`, `add_account()`, `get_accounts()`, `get_messages()`, `mark_read()`, `update_settings()`, etc.
- **`crypto.py`**: Fernet encrypt/decrypt. Key from env.
- **`bot_handlers.py`**: Complete aiogram handlers:
  - `/start` with language selection
  - Account connection flow
  - Inline keyboards for provider selection
  - Notification sender
  - `/accounts`, `/settings`, `/help`
  - i18n middleware injecting translation function
- **`oauth_server.py`**: aiohttp app with routes:
  - `/oauth/gmail/callback` — handle Google OAuth
  - `/oauth/yandex/callback` — handle Yandex OAuth
  - `/api/*` — Mini App REST API with initData validation
- **`sync_engine.py`**: Background loop. Iterates accounts, checks `next_sync_at`, calls provider-specific sync.
- **`sync_gmail.py`**: Gmail API incremental sync using `historyId`.
- **`sync_yandex.py`**: IMAP + XOAUTH2 sync using UID tracking.
- **`classifier.py`**: `classify_yandex_message()` heuristics.
- **`locales/ru.json`**: All Russian strings.
- **`locales/en.json`**: All English strings.
- **`requirements.txt`**: Pinned deps (aiogram, aiohttp, aiosqlite, cryptography, google-api-python-client, google-auth-oauthlib, aioimaplib, pydantic-settings, python-dotenv).
- **`.env.example`**: `BOT_TOKEN`, `ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `YANDEX_CLIENT_ID`, `YANDEX_CLIENT_SECRET`, `BASE_URL`, `MINI_APP_URL`, `DB_PATH`.

### 10.2 Frontend (`mailhub-webapp/`)
- **Full Next.js 16 App Router structure** as in Section 3.3
- **`app/layout.tsx`**: Telegram theme provider, init
- **`app/(app)/inbox/page.tsx`**: Inbox with tabs, account switcher, list
- **`app/(app)/message/[id]/page.tsx`**: Detail view
- **`app/(app)/settings/page.tsx`**: Settings form
- **`components/`**: shadcn/ui components, layout, mail, settings
- **`hooks/`**: useTelegram, useAuth, useMessages
- **`lib/api.ts`**: Typed fetch client with Zod
- **`stores/appStore.ts`**: Zustand
- **`types/index.ts`**: Interfaces
- **`tests/`**: Vitest + Playwright
- **`next.config.js`**
- **`.env.local.example`**: `NEXT_PUBLIC_API_URL`

### 10.3 Documentation
- **`README.md`**:
  - Overview
  - Prerequisites (Python 3.12+, Node 20+, Telegram Bot)
  - Backend setup: `python -m venv venv`, `pip install -r requirements.txt`, fill `.env`, `python main.py`
  - Frontend setup: `npm install`, fill `.env.local`, `npm run dev` / deploy to Vercel
  - How to get Google OAuth credentials
  - How to get Yandex OAuth credentials
  - BotFather setup (description, menu button for Mini App)
  - SQLite backup note (copy `mailhub.db`)

### 10.4 Code Quality
- **Python**: Type hints everywhere, PEP 8, structured logging, no bare excepts, `if __name__ == "__main__": asyncio.run(main())`
- **TypeScript**: Strict mode, no `any`, explicit types
- **Async**: All I/O async, no blocking calls
- **No hardcoded secrets**: Everything from `.env`
- **No TODOs**: Every feature fully implemented

---

## Final Instruction

Write production-ready, clean, simple code following **2026 best practices**. The backend must be a **single Python process** launched with `python main.py` — no Docker, no external databases, no message queues, no separate workers. The frontend must be a modern Next.js 16 Mini App deployed to Vercel. Every external call must have error handling. The UI must feel native to Telegram — warm, minimal, and human. The bot must speak the user's chosen language (Russian or English) perfectly from `/start` to every notification.
