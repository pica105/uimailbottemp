# MailHub — руководство по запуску и эксплуатации на VPS

> Актуальная модель: фиксированная синхронизация каждые 10 секунд, Telegram Mini App с проверкой `initData`, SQLite, два systemd-сервиса и nginx.

## 1. Доступ к серверу

```bash
ssh root@91.186.211.218        # порт 22; пароль хранится отдельно, не в репозитории
```

На VPS находятся: репозиторий `/uimailbot`, Python virtualenv, Node 22 в `/opt/node`, два systemd-сервиса и nginx с HTTPS для `uimail.synergyflow.ru`.

Не публикуйте и не коммитьте `.env`, токены OAuth, Telegram bot token, Fernet-ключ или содержимое базы.

## 2. Из чего состоит проект

| Компонент | Где | Сервис | Порт |
|---|---|---|---|
| Backend (REST API + OAuth) | `/uimailbot/mailhub` | `mailhub` | 8000 |
| Telegram-бот | тот же процесс (`venv/bin/python mailhub/main.py`) | `mailhub` | — |
| Движок синхронизации | тот же процесс | `mailhub` | — |
| Frontend Mini App (Next.js) | `/uimailbot/mailhub-webapp` | `mailhub-web` | 3001 |
| nginx (домен → сервисы) | `/etc/nginx/sites-available/uimail` | `nginx` | 443 |
| SQLite | `/uimailbot/mailhub.db` | — | — |
| Конфиг и секреты | `/uimailbot/mailhub/.env` | — | — |

Маршрутизация nginx:

```text
/       → 127.0.0.1:3001       # Mini App
/api/   → 127.0.0.1:8000       # REST API
/oauth/ → 127.0.0.1:8000       # OAuth callbacks
```

## 3. Запустить backend, бота и frontend

```bash
systemctl start mailhub mailhub-web
```

Backend сначала подключается к Telegram API и регистрирует команды, поэтому HTTP-сервер может стать готовым через 10–15 секунд. Не считайте немедленный `502` после `start` неисправностью — дождитесь health-check.

Надёжная проверка готовности:

```bash
ready=0
for i in $(seq 1 30); do
  backend=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/api/health)
  frontend=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3001/inbox)
  if [ "$backend" = 200 ] && [ "$frontend" = 200 ]; then
    echo "ready after ${i}s"
    ready=1
    break
  fi
  sleep 1
done
[ "$ready" = 1 ] || { echo 'services did not become ready'; exit 1; }

systemctl is-active mailhub mailhub-web
curl -sk https://127.0.0.1/api/health       # {"status":"ok"}
curl -sk -o /dev/null -w '%{http_code}\n' https://uimail.synergyflow.ru/inbox
ss -tln | grep -E ':(8000|3001) '
```

Откройте Mini App из Telegram через кнопку бота «Открыть в MailHub». Обычный браузер намеренно показывает заглушку «Откройте MailHub в Telegram» и не загружает защищённые данные.

### Запуск backend вручную

Только если systemd не используется:

```bash
cd /uimailbot
venv/bin/python mailhub/main.py
```

Не запускайте параллельно ручной процесс и systemd-сервис: они будут конкурировать за Telegram long polling и порты.

## 4. Остановить всё

```bash
systemctl stop mailhub mailhub-web
systemctl is-active mailhub mailhub-web
```

`mailhub-web` настроен с `SuccessExitStatus=143`: штатная остановка через SIGTERM не должна считаться ошибкой. Если старый флаг `failed` остался после предыдущего запуска, очистите только статус systemd:

```bash
systemctl reset-failed mailhub-web
```

## 5. Автозапуск после перезагрузки

```bash
systemctl enable mailhub mailhub-web
systemctl is-enabled mailhub mailhub-web
```

## 6. Логи

```bash
journalctl -u mailhub -f
journalctl -u mailhub-web -f
journalctl -u mailhub --since '15 min ago' --no-pager
```

Полезный фильтр backend/API:

```bash
journalctl -u mailhub --since '15 min ago' --no-pager \
  | grep -E 'Mini App auth rejected|aiohttp.access.*api/|ERROR|Traceback'
```

Сетевые disconnect-ошибки Telegram при остановке или кратковременном сбое сети возможны. Ищите устойчивые повторяющиеся ошибки синхронизации, OAuth и API, а не единичную запись при shutdown.

## 7. Обновить код из GitHub

Перед pull проверьте локальное состояние. Не затирайте `.env`, `mailhub.db` и `venv/`. Нормально, если `venv/` отображается как локальная untracked-папка. После npm install также может измениться `mailhub-webapp/package-lock.json`; сначала проверьте diff. Если это только автоматически созданное локальное изменение без намеренных правок, восстановите только lock-файл:

```bash
set -e
cd /uimailbot
df -h /
git status --short
# Если tracked-изменения есть, сначала сохраните их в stash; venv/ не трогайте.
stamp=$(date +%Y%m%d-%H%M%S)
backend_recovery=1
trap '[ "$backend_recovery" = 1 ] && systemctl start mailhub || true' EXIT
systemctl stop mailhub
mkdir -p backups
gzip -c mailhub.db > "backups/mailhub-${stamp}.db.gz"
git stash push -m "vps-predeploy-${stamp}" -- .
if ! git pull --ff-only; then
  echo 'git pull failed; previous backend will be started by trap'
  exit 1
fi
systemctl start mailhub
backend_recovery=0
trap - EXIT
for i in $(seq 1 30); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/health || true)
  [ "$code" = 200 ] && break
  sleep 1
done

# Проверка production SQLite без записи:
venv/bin/python - <<'PY'
import sqlite3
c = sqlite3.connect("file:/uimailbot/mailhub.db?mode=ro", uri=True, timeout=2)
print("foreign_key_check:", list(c.execute("PRAGMA foreign_key_check")))
print("integrity_check:", c.execute("PRAGMA integrity_check").fetchone()[0])
c.close()
PY
```

Если есть другие modified tracked files, остановитесь и разберите их вручную — не используйте `git reset --hard`.

### Экономная пересборка frontend

Сначала проверьте место и наличие dev-зависимостей:

```bash
cd /uimailbot/mailhub-webapp
df -h /
for p in next tailwindcss typescript @tailwindcss/postcss; do
  node -e "require.resolve('$p')" || echo "missing: $p"
done
```

Если зависимости уже установлены, повторный `npm install` не нужен:

```bash
export PATH=/opt/node/bin:$PATH
export NEXT_TELEMETRY_DISABLED=1
export NODE_OPTIONS=--max-old-space-size=512
rm -rf .next
npm run build
cd /uimailbot
venv/bin/python -m py_compile mailhub/oauth_server.py mailhub/main.py
systemctl restart mailhub-web
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3001/inbox || true)
  [ "$code" = 200 ] && break
  sleep 1
done
```

Если dev-зависимости действительно нужно восстановить, делайте это только после проверки свободного места и направляйте npm-кэш в RAM. Playwright browsers на VPS не скачивайте — e2e запускайте локально:

```bash
cd /uimailbot/mailhub-webapp
df -h /
export PATH=/opt/node/bin:$PATH
export NPM_CONFIG_CACHE=/dev/shm/npm-cache
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export NEXT_TELEMETRY_DISABLED=1
export NODE_OPTIONS=--max-old-space-size=512
npm install --include=dev --no-audit --no-fund --loglevel=error
rm -rf /dev/shm/npm-cache /tmp/npm-cache
npm run build
cd /uimailbot
venv/bin/python -m py_compile mailhub/oauth_server.py mailhub/main.py
systemctl restart mailhub mailhub-web
```

Не запускайте `npm prune --omit=dev` до завершения сборки и тестов: команда удаляет Tailwind/PostCSS/TypeScript, после чего следующая сборка может упасть. На VPS с маленьким диском не скачивайте Playwright browsers.

После сборки проверьте:

```bash
systemctl is-active mailhub mailhub-web
curl -sk https://127.0.0.1/api/health
curl -sk -o /dev/null -w '%{http_code}\n' https://uimail.synergyflow.ru/inbox
curl -sk https://uimail.synergyflow.ru/inbox \
  | grep -o 'https://telegram.org/js/telegram-web-app.js[^" ]*'
```

## 8. Подключить почтовые ящики

1. Откройте бота в Telegram и отправьте `/start`.
2. Используйте единую reply-клавиатуру: «Мои аккаунты», «Подключить», «Настройки», «Помощь».
3. Откройте Mini App кнопкой меню рядом с полем ввода; backend регистрирует её через `setChatMenuButton`.
4. В «📬 Мои аккаунты» нажмите подключение и выберите Gmail или Яндекс.
5. Пройдите OAuth в браузере и вернитесь в Telegram.
6. После подключения начнётся импорт последних 50 писем без массовых уведомлений.

Команды не нужны для обычной навигации. `/start` оставлен как ручной legacy/deep-link вход; старые `/accounts`, `/settings`, `/help` продолжают работать.

## 9. Gmail: scope для mark-as-read

Статус «прочитано» пишется локально сразу, а затем фоновая задача отправляет его в настоящий ящик:

- Яндекс: IMAP `STORE +FLAGS (\\Seen)`;
- Gmail: API `messages.modify`, снятие метки `UNREAD`.

Gmail требует OAuth scope `gmail.modify`. Старый аккаунт с readonly-токеном получит 403 при записи в Gmail; приложение не должно падать, но удалённая метка не изменится.

Исправление: `/accounts` → удалить старый Gmail-аккаунт → подключить его заново через OAuth. После новой авторизации проверьте логи и отметьте тестовое письмо прочитанным.

## 10. Авторизация Telegram Mini App

Frontend подключает официальный SDK до интерактивного кода Next.js:

```text
https://telegram.org/js/telegram-web-app.js?1
```

SDK предоставляет `Telegram.WebApp.initData`. Frontend передаёт подписанную строку в каждом защищённом запросе:

```text
X-Telegram-Init-Data: <signed initData>
```

Backend проверяет HMAC-SHA256, bot token и срок `auth_date`. `/api/health` публичен; остальные `/api/*` требуют валидную подпись.

Telegram Web/Desktop и мобильные клиенты могут использовать разные WebView и User-Agent. User-Agent не является доказательством авторизации — источник истины `X-Telegram-Init-Data`.

Если SDK появляется с задержкой, frontend повторно проверяет `initData` в первые 1000 мс и не запускает protected queries до его появления. Query-кэш разделён по Telegram user ID. `initData` не сохраняется в localStorage и не пишется в логи.

### Диагностика ошибки «доступа нет»

```bash
# 1. SDK есть в production HTML?
curl -sk https://uimail.synergyflow.ru/inbox \
  | grep -o 'https://telegram.org/js/telegram-web-app.js[^" ]*'

# 2. Что видел backend?
journalctl -u mailhub --since '15 min ago' --no-pager \
  | grep -E 'Mini App auth rejected|aiohttp.access.*api/'
```

Расшифровка auth-лога:

- `has_init_data=False` — заголовок не пришёл: SDK не загрузился, приложение открыто не из Telegram или запрос ушёл слишком рано;
- `has_init_data=True` — строка пришла, но подпись, формат или срок действия не прошли проверку.

Backend не логирует саму `initData`. Не копируйте её в issue, скриншоты или сообщения поддержки.

## 11. Фиксированный интервал синхронизации

Интервал не настраивается пользователем: каждый аккаунт проверяется ровно через **10 секунд** после успешного синка, начиная с момента подключения (`POLL_FIXED_SECONDS = 10`).

- после подключения первый синк выполняется сразу, дальше — каждые 10 секунд;
- внутренний цикл движка просыпается каждые 5 секунд и обрабатывает аккаунты, которым уже пора синхронизироваться;
- ошибки не вызывают бесконечные запросы к провайдеру: экспоненциальный backoff `60с, 120с, 240с...` с потолком 1 час; после успешного синка счётчик ошибок сбрасывается.

В настройках (и в боте, и в Mini App) информации об интервале нет: он фиксированный.

## 12. Полезные команды и диск

На VPS жёсткое ограничение по месту. Перед сборкой и установкой проверяйте:

```bash
df -h /
free -m
du -sh /uimailbot/* /var/log/* /tmp/* 2>/dev/null | sort -rh | head
```

Безопасная очистка кэшей:

```bash
apt-get clean
journalctl --vacuum-size=20M
rm -rf /tmp/npm-cache /dev/shm/npm-cache
```

Бэкап базы перед миграциями (только после остановки backend):

```bash
mkdir -p /uimailbot/backups
stamp=$(date +%Y%m%d-%H%M%S)
systemctl stop mailhub
gzip -c /uimailbot/mailhub.db > "/uimailbot/backups/mailhub-${stamp}.db.gz"
systemctl start mailhub
```

Не удаляйте `mailhub.db`, `.env` или `venv/` для освобождения места без отдельного плана восстановления.

## 13. Статус функций

| Функция | Статус |
|---|---|
| Синхронизация Gmail + Яндекс | ✅ инкрементальная |
| Интервал синхронизации | ✅ фиксированный 10с, без ручного выбора |
| Telegram-уведомления | ✅; Promo/Spam подавляются всегда |
| API accounts/messages/settings/mark-read | ✅ при валидном Telegram initData; messages: `has_more` pagination |
| Mark-read Яндекс | ✅ после provider-запроса |
| Mark-read Gmail | ⚠️ нужен scope `gmail.modify`; старый readonly-токен требует переподключения |
| OAuth | ✅ |
| Telegram Mini App SDK/auth | ✅ официальный SDK + HMAC-проверка |
| Работа в обычном браузере | ⚠️ заглушка без доступа к данным — ожидаемое поведение |

## 14. Быстрый чек-лист после перезагрузки VPS

```bash
systemctl start mailhub mailhub-web

ready=0
for i in $(seq 1 30); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/api/health)
  if [ "$code" = 200 ]; then
    ready=1
    break
  fi
  sleep 1
done
[ "$ready" = 1 ] || { echo 'backend did not become ready'; exit 1; }

systemctl is-active mailhub mailhub-web
curl -sk https://127.0.0.1/api/health
curl -sk -o /dev/null -w 'Mini App HTTP %{http_code}\n' https://uimail.synergyflow.ru/inbox
```

Для внешнего API-теста с локального компьютера:

```bash
./.venv/bin/python scripts/external_api_test.py
```

Тест проверяет публичный health, ожидаемый 401 без initData, авторизованные accounts/settings/messages/mark-read и сохранение настроек по HTTPS-домену.
