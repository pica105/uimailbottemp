# MailHub Backend

## Стек

- **Язык:** Python 3.12+
- **Бот:** aiogram 3.x (long polling, HTML parse mode)
- **HTTP:** aiohttp — REST API Mini App + OAuth-колбэки
- **БД:** SQLite через aiosqlite (один файл `mailhub.db`)
- **IMAP:** aioimaplib 2.x (Яндекс, XOAUTH2)
- **Шифрование:** cryptography / Fernet (токены в БД)
- **Конфиг:** pydantic-settings, `.env` рядом с пакетом

Один asyncio-процесс (`python -m mailhub.main`) поднимает HTTP-сервер, poller бота и движок синхронизации. Graceful shutdown по SIGINT/SIGTERM. HTTP-сервер слушает только после инициализации Telegram bot API, поэтому после `systemctl start` health-check нужно выполнять в цикле или подождать примерно 10–15 секунд.

## Модули

| Файл | Назначение |
|---|---|
| `main.py` | Точка входа: бот + HTTP + sync loop |
| `config.py` | Pydantic-settings, валидация env (ключ Fernet, токен) |
| `database.py` | aiosqlite: схема + все запросы |
| `crypto.py` | Fernet encrypt/decrypt |
| `bot_handlers.py` | aiogram: /start, /accounts, /settings, /help, OAuth-кнопки, уведомления, i18n |
| `oauth_server.py` | aiohttp: OAuth-колбэки, REST API, проверка initData (HMAC-SHA256), auth diagnostics |
| `sync_engine.py` | Фоновый цикл, эластичный интервал, бэкофф ошибок, нотификации |
| `sync_gmail.py` | Gmail REST: инкрементальный синк, mark-read через `messages.modify` |
| `sync_yandex.py` | Yandex IMAP XOAUTH2: UID-инкремент, STORE `\Seen` |
| `mark_read.py` | Best-effort прокидывание «прочитано» в провайдера (fire-and-forget) |
| `classifier.py` | Эвристики категорий (important/promo/spam/social/other); promo/spam подавляются |
| `locales/` | ru.json, en.json |

## Авторизация Mini App

Все `/api/*`, кроме `/api/health`, требуют заголовок:

```text
X-Telegram-Init-Data: <signed Telegram WebApp initData>
```

`_init_data_middleware` в `oauth_server.py`:

1. разбирает query-string Telegram;
2. строит data-check-string;
3. вычисляет секрет через `HMAC-SHA256(WebAppData, BOT_TOKEN)`;
4. сравнивает подпись constant-time;
5. отклоняет просроченный `auth_date` старше 24 часов;
6. извлекает Telegram user ID и передаёт его обработчикам.

Проверка владельца выполняется отдельно в каждом endpoint: письма и аккаунты выдаются только владельцу. Чужой numeric ID возвращает 404, чтобы не раскрывать существование объекта.

### Диагностика 401

При недействительном или отсутствующем initData backend возвращает `401`:

```json
{"error":"unauthorized","message":"Invalid or expired initData"}
```

В warning-лог попадает безопасная метаинформация: method, path, `has_init_data`, ограниченный User-Agent и только path из Referer. Полная подписанная строка initData никогда не логируется.

Интерпретация:

- `has_init_data=False` — frontend не получил SDK/initData или запрос пришёл не из Telegram;
- `has_init_data=True` — строка присутствует, но подпись/срок/формат не прошли проверку;
- валидные API-вызовы должны появляться в `aiohttp.access` со статусом 200.

Проверка на VPS:

```bash
journalctl -u mailhub --since '15 min ago' --no-pager \
  | grep -E 'Mini App auth rejected|aiohttp.access.*api/'
```

## Синхронизация

Цикл движка просыпается каждые `SYNC_BASE_INTERVAL_SECONDS` (5 с) и синкает аккаунты, у которых `next_sync_at <= now`.

**Gmail (REST):**
- Bootstrap: `messages.list` (последние 50) + до 50 последних непрочитанных (`is:unread in:inbox`) + `users.getProfile` → стартовый `historyId`
- Дальше: все страницы `users.history` от checkpoint'а (`historyTypes=messageAdded`), дедупликация по id
- Если Gmail вернул устаревший history id (404), выполняется новый bootstrap вместо долгого backoff
- Полное тело: `messages.get` (format=full), парсинг payload → text/plain

**Яндекс (IMAP):**
- `imap.yandex.ru:993`, XOAUTH2 через нативный `xoauth2()` (aioimaplib 2.x)
- `uid_search("ALL")`, фильтр `uid >= checkpoint`, батч 50, новые письма первыми
- Для старых аккаунтов один раз выполняется `uid_search("UNSEEN")`, чтобы восстановить свежие непрочитанные письма; флаг хранится в `mail_accounts.unread_bootstrap_done`
- `BODY.PEEK[]` (не меняет флаг), разбор MIME (RFC 2047-заголовки, HTML→текст)

**Эластичный интервал (на аккаунт):**

```text
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

Все `/api/*`, кроме health, требуют валидный `X-Telegram-Init-Data`.

```text
GET    /api/health
GET    /api/accounts
DELETE /api/accounts/{id}
GET    /api/accounts/{id}/messages?category=&limit=20&offset=  # response also has_more
GET    /api/messages/{id}
POST   /api/messages/{id}/read
GET    /api/settings
PATCH  /api/settings
```

OAuth callbacks — отдельный browser redirect flow, который использует сохранённый
одноразовый `state` из БД:

```text
GET /oauth/gmail/callback?code=&state=
GET /oauth/yandex/callback?code=&state=
```

## Безопасность

- Токены почты — Fernet-шифрованные в БД, ключ только в env
- initData подписан Telegram'ом, проверяется на каждом защищённом запросе
- initData не сохраняется в логах, localStorage или query-кэше
- Query-кэш frontend разделяется по Telegram user ID
- Права: письма отдаются только владельцу аккаунта (404 для чужих id)

## Деплой (VPS)

- **systemd `mailhub`:** `venv/bin/python -m mailhub.main`, порт 8000, Restart=always
- **systemd `mailhub-web`:** `next start -p 3001` (фронт)
- **nginx** (`uimail.synergyflow.ru`): `/` → 3001, `/api/` и `/oauth/` → 8000, TLS
- **Пути:** репо `/uimailbot`, venv `/uimailbot/venv`, БД `/uimailbot/mailhub.db`, Node 22 `/opt/node`
- На VPS мало места: сборка должна использовать RAM-кэш npm и не скачивать Playwright browsers. Не выполнять `npm prune --omit=dev` до завершения сборки и тестов.

## Операции

```bash
systemctl start mailhub mailhub-web
systemctl stop mailhub mailhub-web
systemctl restart mailhub mailhub-web
journalctl -u mailhub -f
systemctl status mailhub mailhub-web
curl -sk https://127.0.0.1/api/health
```

После запуска backend может отвечать не сразу. Надёжный health-check:

```bash
for i in $(seq 1 30); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/api/health)
  [ "$code" = 200 ] && break
  sleep 1
done
```

Тесты: `./.venv/bin/python scripts/smoke_test.py` (8 проверок: crypto, классификатор, БД, initData HMAC, OAuth URL, Gmail-хелперы, Yandex-парсер, эластичный интервал), `scripts/api_simulation.py` (живой HTTP + все эндпоинты) и `scripts/external_api_test.py` (публичный домен + валидный initData).
