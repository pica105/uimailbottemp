# MailHub — Обзор проекта

## Что это

**MailHub** — Telegram-бот для работы с почтой Gmail и Яндекс прямо в Telegram. Подключение через OAuth, уведомления о новых письмах в чат, полный инбокс в Mini App без установки отдельного приложения. Бот и Mini App — один проект, два компонента: Python-бекенд (aiogram + aiohttp + SQLite) и Next.js-фронтенд.

## Как это работает

### 1. Подключение аккаунта

1. `/start` → выбор языка (ru/en) → пользователь создаётся в БД.
2. `/accounts` → «Подключить Gmail/Яндекс» → бот шлёт OAuth-ссылку.
3. Авторизация в браузере → callback `{BASE_URL}/oauth/{provider}/callback`.
4. Обмен code → tokens, шифрование Fernet, сохранение в SQLite.
5. Первый импорт 50 последних писем — **без** флуда уведомлениями (`mark_all_notified`).

### 2. Синхронизация

1. Каждые `SYNC_BASE_INTERVAL_SECONDS` (5 с) движок просматривает активные аккаунты.
2. Gmail — REST `users.history` от checkpoint; Яндекс — IMAP UID-инкремент.
3. Новые письма → кэш SQLite + уведомление в Telegram, кроме muted-категорий.
4. Интервал у каждого аккаунта автоматический: новое письмо → 10 с, тишина → рост до 5 мин; ошибки → экспоненциальный backoff.

Пользователь не выбирает частоту синхронизации. Диапазон 10 секунд–5 минут — внутренняя политика движка.

### 3. Открытие Mini App

Кнопка «Открыть в MailHub» из бота открывает `MINI_APP_URL`. Frontend подключает официальный `telegram-web-app.js` до интерактивного Next.js-кода, вызывает `ready()`/`expand()` и получает подписанный `Telegram.WebApp.initData`.

Каждый защищённый API-запрос отправляет:

```text
X-Telegram-Init-Data: <signed initData>
```

Backend валидирует подпись и срок действия, извлекает Telegram user ID и ограничивает доступ его аккаунтами и письмами.

На Telegram Web SDK может завершить инициализацию чуть позже загрузки HTML. Frontend повторно читает initData в течение первой секунды и не запускает protected queries, пока данные не появились. Если SDK отсутствует, показывается понятная заглушка «Откройте MailHub в Telegram», а не ложное «аккаунты не подключены».

### 4. Разные устройства

Один пользователь может открывать Mini App с телефона, Telegram Desktop и Telegram Web. Запросы каждого открытия несут подпись текущей Telegram-сессии. Frontend не сохраняет initData в localStorage, а query-кэш разделён по Telegram user ID. Поэтому смена пользователя в одном WebView не должна показывать кэш предыдущего пользователя.

Диагностика проблем доступа:

```bash
journalctl -u mailhub --since '15 min ago' --no-pager \
  | grep -E 'Mini App auth rejected|aiohttp.access.*api/'
```

`has_init_data=False` означает, что заголовок не пришёл; `has_init_data=True` — подпись или срок действия не прошли. Сама initData в логах не записывается.

### 5. Просмотр и действия

1. Inbox: категории All/Important/Promo/Spam, аккаунты, просмотр письма.
2. «Прочитано»: оптимистичное обновление UI + фоновая отправка статуса в ящик.
3. Gmail: `messages.modify`; Яндекс: `STORE +FLAGS (\Seen)`.

### 6. Настройки

- Язык интерфейса и Telegram-бота: ru/en.
- Muted-категории уведомлений.
- Интервал синхронизации: только автоматический, 10с–5мин; ручного селектора нет.

## Репозиторий и runtime

- **GitHub:** `git@github.com:pica105/uimailbottemp.git`, ветка `main`
- **VPS:** `/uimailbot`
- **Backend + bot + sync:** systemd `mailhub`, `127.0.0.1:8000`
- **Mini App:** systemd `mailhub-web`, `127.0.0.1:3001`
- **nginx:** `uimail.synergyflow.ru`, HTTPS; `/api/` и `/oauth/` → backend
- **SQLite:** `/uimailbot/mailhub.db`

## Статус последнего проверочного snapshot

Ниже зафиксирован результат проверки commit `722da9d` на момент последнего деплоя. Перед эксплуатационными решениями повторяйте health/API-проверки: статус и свободное место на VPS меняются со временем.

| Компонент | Статус |
|---|---|
| Backend compile/smoke/API simulation | ✅ пройдено |
| Frontend typecheck/Vitest/build/lint | ✅ пройдено; lint без ошибок, 2 warning |
| Telegram SDK в production HTML | ✅ присутствует |
| Authenticated API по публичному домену | ✅ accounts/settings/messages/mark-read |
| Запрос без initData | ✅ корректный 401 |
| Синхронизация Gmail + Яндекс | ✅ работает; runtime ошибки не обнаружены в последней проверке |
| Эластичный интервал 10с→5мин | ✅ автоматический |
| Уведомления Telegram | ✅ |
| Mark-read Яндекс | ✅ STORE `\Seen` |
| Mark-read Gmail | ⚠️ требует OAuth scope `gmail.modify`; старый readonly-токен даёт 403, нужно переподключить аккаунт |
| Сервисы на VPS | ✅ `mailhub` и `mailhub-web` active |
| nginx / HTTPS | ✅ health и Mini App отвечают 200 |

На момент этого snapshot на VPS было около 254 МБ свободно после восстановления frontend dev-зависимостей. Это не постоянная гарантия: перед сборкой всегда проверяйте `df -h /`; кэш npm направляйте в `/dev/shm`.

## История

- Август 2026: деплой на VPS, инкрементальная синхронизация, анти-флуд уведомлений, автоматический интервал 10с–5мин, mark-read с прокидыванием в провайдера, Telegram Mini App auth и внешние проверки по HTTPS-домену.
