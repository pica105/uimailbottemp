# MailHub Backend

## Стек

- **Язык:** Python 3.12+
- **Бот:** aiogram 3.x (long polling, HTML parse mode)
- **HTTP:** aiohttp — REST API Mini App + OAuth-колбэки
- **БД:** SQLite через aiosqlite (один файл `mailhub.db`)
- **IMAP:** aioimaplib 2.x (Яндекс, XOAUTH2)
- **Шифрование:** cryptography / Fernet (токены в БД)
- **Конфиг:** pydantic-settings, `.env` рядом с пакетом

Один asyncio-процесс (`python -m mailhub.main`) поднимает три корутины: поллер бота, HTTP-сервер и движок синхронизации. Graceful shutdown по SIGINT/SIGTERM.

## Модули

| Файл | Назначение |
|---|---|
| `main.py` | Точка входа: бот + HTTP + sync loop |
| `config.py` | Pydantic-settings, валидация env (ключ Fernet, токен) |
| `database.py` | aiosqlite: схема + все запросы |
| `crypto.py` | Fernet encrypt/decrypt |
| `bot_handlers.py` | aiogram: /start, /accounts, /settings, /help, OAuth-кнопки, уведомления, i18n |
| `oauth_server.py` | aiohttp: OAuth-колбэки, REST API, проверка initData (HMAC-SHA256) |
| `sync_engine.py` | Фоновый цикл, эластичный интервал, бэкофф ошибок, нотификации |
| `sync_gmail.py` | Gmail REST: инкрементальный синк, mark-read через `messages.modify` |
| `sync_yandex.py` | Yandex IMAP XOAUTH2: UID-инкремент, STORE `\Seen` |
| `mark_read.py` | Best-effort прокидывание «прочитано» в провайдера (fire-and-forget) |
| `classifier.py` | Эвристики категорий (important/promo/spam/other) |
| `locales/` | ru.json, en.json |

## Синхронизация

Цикл движка просыпается каждые `SYNC_BASE_INTERVAL_SECONDS` (5 с) и синкает аккаунты, у которых `next_sync_at <= now`.

**Gmail (REST):**
- Первый импорт: `messages.list` (последние 50) + `users.getProfile` → стартовый `historyId`
- Дальше: `users.history` от checkpoint'а (`historyTypes=messageAdded`), дедупликация по id
- Полное тело: `messages.get` (format=full), парсинг payload → text/plain

**Яндекс (IMAP):**
- `imap.yandex.ru:993`, XOAUTH2 через нативный `xoauth2()` (aioimaplib 2.x)
- `uid_search("ALL")`, фильтр `uid >= checkpoint`, батч 50, новые письма первыми
- `BODY.PEEK[]` (не меняет флаг), разбор MIME (RFC 2047-заголовки, HTML→текст)

**Эластичный интервал (на аккаунт):**

```
interval = max(POLL_MIN, min(POLL_MAX, idle_seconds // 10))
POLL_MIN = 10с, POLL_MAX = 300с
```

Интервал полностью автоматический, ручная настройка отсутствует. Свежее письмо → 10 с. Тихий ящик → рост к потолку (5 мин). Ошибки: `next_sync_at = now + min(2^n * 60, 3600)`.

**Mark-read:** API/бот ставят `is_read` локально и через `mark_read.py` (фоновая задача) отправляют в провайдер: Gmail `messages.modify` (`removeLabelIds: ["UNREAD"]`), Яндекс `STORE +FLAGS (\Seen)`. Провайдер-фейл не ломает локальный ответ. Для Gmail нужен scope `gmail.modify` — старые токены (readonly) дают 403, нужно переподключить аккаунт.

## OAuth-поток

1. `/start` → язык → `/accounts` → «Подключить Gmail/Яндекс»
2. Бот генерирует URL: `{BASE_URL}/oauth/{provider}/callback` (state хранится в БД, TTL 600 с)
3. Колбэк: обмен code → tokens, шифрование Fernet, сохранение
4. Скоупы: Gmail — `gmail.modify`; Яндекс — `login:email` + `mail:imap_full`
5. Бот: «Аккаунт подключён», первый импорт без флуда уведомлений (`mark_all_notified`)

## REST API (Mini App)

Все `/api/*` требуют `X-Telegram-Init-Data` (валидация HMAC-SHA256 от `WebAppData` + bot token).

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

## Безопасность

- Токены почты — Fernet-шифрованные в БД, ключ только в env
- initData подписан Telegram'ом, проверяется на каждом запросе
- Права: письма отдаются только владельцу аккаунта (404 для чужих id)

## Деплой (VPS 91.186.211.218)

- **systemd `mailhub`:** `venv/bin/python -m mailhub.main`, порт 8000, Restart=always
- **systemd `mailhub-web`:** `next start -p 3001` (фронт)
- **nginx** (`uimail.synergyflow.ru`): `/` → 3001, `/api/` и `/oauth/` → 8000, TLS
- **Пути:** репо `/uimailbot`, venv `/uimailbot/venv`, БД `/uimailbot/mailhub.db`, Node 22 `/opt/node`
- **Диск 1 ГБ** — пересборка фронта только экономная (кэш npm в `/dev/shm`, `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`, `npm prune --omit=dev` после build)

## Операции

```bash
systemctl start|stop|restart mailhub mailhub-web
journalctl -u mailhub -f                          # бекенд + бот + синк
systemctl status mailhub mailhub-web
curl -sk https://127.0.0.1/api/health             # {"status":"ok"}
```

Тесты: `./.venv/bin/python scripts/smoke_test.py` (8 проверок: crypto, классификатор, БД, initData HMAC, OAuth URL, Gmail-хелперы, Yandex-парсер, эластичный интервал) и `scripts/api_simulation.py` (живой HTTP + все эндпоинты).
