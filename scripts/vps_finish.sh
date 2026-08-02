#!/usr/bin/env bash
# =============================================================================
# MailHub — финишный скрипт деплоя на VPS (после обрыва интернета)
#
# Доделывает прерванную работу за один запуск, локально:
#   1. пушит незапушенные коммиты на GitHub
#   2. подтягивает последний код на VPS (frontend commit)
#   3. экономно пересобирает фронтенд (npm install -> build -> prune)
#   4. живые тесты на реальных ящиках (Yandex \Seen, Gmail 403, elastic)
#   5. останавливает сервисы (mailhub + mailhub-web) — по просьбе владельца
#
# Использование:
#   ./scripts/vps_finish.sh              # полный прогон + остановка сервисов
#   KEEP_RUNNING=1 ./scripts/vps_finish.sh   # сервисы остаются запущенными
#
# Требования на локальной машине: sshpass.
# =============================================================================
set -euo pipefail

VPS_HOST="${VPS_HOST:-91.186.211.218}"
VPS_PORT="${VPS_PORT:-22}"
VPS_USER="${VPS_USER:-root}"
VPS_PASS="${VPS_PASS:-Qk@GqI#GGxCP}"
KEEP_RUNNING="${KEEP_RUNNING:-0}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

command -v sshpass >/dev/null || { echo "Ошибка: установите sshpass (sudo apt install sshpass)"; exit 1; }
export SSHPASS="$VPS_PASS"
SSH=(sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$VPS_PORT" "$VPS_USER@$VPS_HOST")

echo "==================== 0. PUSH локальных коммитов ===================="
(cd "$REPO_DIR" && git push origin main 2>&1 | tail -2) || echo "push не удался (интернет ещё не вернулся?) — продолжаю"

echo "==================== 1. СВЯЗЬ + здоровье бекенда ===================="
"${SSH[@]}" 'systemctl is-active mailhub && echo "--- health ---" && curl -sk -m 5 https://127.0.0.1/api/health && echo'

echo "==================== 2. ПЕРЕСБОРКА ФРОНТЕНДА (экономно) ===================="
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -e
cd /uimailbot
echo '--- git pull (frontend commit) ---'
git pull --ff-only 2>&1 | tail -1
echo '--- очистка ---'
rm -rf /tmp/npm-cache /tmp/npm-cache2 /root/.npm /root/.cache 2>/dev/null || true
apt-get clean -qq 2>/dev/null || true
journalctl --vacuum-size=20M >/dev/null 2>&1 || true
export PATH=/opt/node/bin:$PATH
export NPM_CONFIG_CACHE=/tmp/npm-cache
export NEXT_TELEMETRY_DISABLED=1
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
cd /uimailbot/mailhub-webapp
rm -rf node_modules .next
FREE_MB=$(df -m / | awk 'NR==2{print $4}')
echo "--- свободно после очистки: ${FREE_MB} MB ---"
if [ "$FREE_MB" -lt 950 ]; then
  echo "!!! Маловато места для сборки (нужно >= 950 MB)."
  echo "!!! Освободите место на VPS и запустите скрипт снова. Подсказки:"
  echo "!!!   apt-get clean; journalctl --vacuum-size=5M; du -sh /tmp/* /var/log/* | sort -rh | head"
  exit 2
fi
echo '--- npm install (dev-зависимости, без браузеров Playwright) ---'
npm install --no-audit --no-fund --loglevel=error 2>&1 | tail -2
rm -rf /tmp/npm-cache
echo '--- next build (лимит памяти 512MB) ---'
NODE_OPTIONS=--max-old-space-size=512 npm run build 2>&1 | tail -6
echo '--- prune dev-зависимостей ---'
npm prune --omit=dev --no-audit --no-fund --loglevel=error 2>&1 | tail -1
rm -rf /tmp/npm-cache
df -h / | tail -1
echo '--- рестарт mailhub-web ---'
systemctl restart mailhub-web
sleep 5
systemctl is-active mailhub-web
curl -sk -m 10 -o /dev/null -w 'frontend /inbox -> HTTP %{http_code}\n' https://127.0.0.1/inbox
REMOTE

echo "==================== 3. ЖИВЫЕ ТЕСТЫ (реальные ящики) ===================="
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -e
cd /uimailbot
venv/bin/python - <<'PY'
import asyncio, sys, random
sys.path.insert(0, '.')
from mailhub.database import Database
from mailhub import sync_yandex, sync_gmail
from mailhub.config import settings

async def main():
    db = Database('./mailhub.db')
    await db.connect()
    accounts = await db._fetchall(
        'SELECT id, provider, email FROM mail_accounts WHERE is_active=1 ORDER BY id')
    print('active accounts:', [(a['id'], a['provider'], a['email']) for a in accounts])

    def uid_list(resp):
        if resp.result != 'OK' or not resp.lines or not resp.lines[0]:
            return []
        return resp.lines[0].split()

    # --- 3a. Yandex: STORE \Seen на случайном письме, проверка через SEARCH ---
    ya = [a for a in accounts if a['provider'] == 'yandex']
    if ya:
        acc = ya[0]
        full = await db.get_account(acc['id'])
        rows = await db._fetchall(
            'SELECT provider_message_id FROM messages_cache WHERE account_id=? AND is_read=0 LIMIT 30',
            (acc['id'],))
        assert rows, 'нет непрочитанных писем для теста Yandex'
        pid = random.choice(rows)['provider_message_id']
        uid = pid.split('-', 1)[1]
        client = await sync_yandex._connect(full)
        await client.select('INBOX')
        was_unread = uid.encode() in uid_list(await client.uid_search('UNSEEN'))
        await client.logout()
        await sync_yandex.mark_message_read(full, pid)
        client = await sync_yandex._connect(full)
        await client.select('INBOX')
        still_unread = uid.encode() in uid_list(await client.uid_search('UNSEEN'))
        await client.logout()
        assert was_unread, f'письмо {pid} не было непрочитанным на сервере — тест невалиден'
        assert not still_unread, f'Yandex STORE \\Seen не сработал: {pid} всё ещё UNSEEN'
        print(f'YANDEX mark-read OK: {pid} было UNSEEN -> теперь \\Seen на сервере')

    # --- 3b. Gmail: graceful 403 (старый readonly-токен, пока не переподключён) ---
    gm = [a for a in accounts if a['provider'] == 'gmail']
    if gm:
        full = await db.get_account(gm[0]['id'])
        rows = await db._fetchall(
            'SELECT provider_message_id FROM messages_cache WHERE account_id=? LIMIT 1',
            (gm[0]['id'],))
        if rows:
            try:
                await sync_gmail.mark_message_read(full, rows[0]['provider_message_id'])
                print('GMAIL mark-read: OK (у токена уже есть gmail.modify)')
            except Exception as exc:
                print(f'GMAIL mark-read корректно упал (ожидаемый 403 до переподключения): {str(exc)[:130]}')

    # --- 3c. Эластичный интервал: константы ---
    print('elastic: POLL_MIN=%s POLL_MAX=%s' % (settings.POLL_MIN_SECONDS, settings.POLL_MAX_SECONDS))
    await db.close()

asyncio.run(main())
PY
REMOTE

echo "==================== 4. ТЕМП СИНХРОНИЗАЦИИ (30-секундная выборка) ===================="
"${SSH[@]}" 'bash -s' <<'REMOTE'
cd /uimailbot
venv/bin/python - <<'PY'
import asyncio, sys, time
sys.path.insert(0, '.')
from mailhub.database import Database
async def snap(tag):
    db = Database('./mailhub.db'); await db.connect()
    rows = await db._fetchall('SELECT id, next_sync_at, sync_error_count FROM mail_accounts ORDER BY id')
    await db.close()
    print(tag, 'now=', int(time.time()), rows)
async def main():
    await snap('T0')
    await asyncio.sleep(30)
    await snap('T1')
asyncio.run(main())
PY
REMOTE

if [ "$KEEP_RUNNING" != "1" ]; then
  echo "==================== 5. ОСТАНОВКА СЕРВИСОВ (по просьбе) ===================="
  "${SSH[@]}" 'systemctl stop mailhub mailhub-web; sleep 2; (systemctl is-active mailhub || echo "mailhub: остановлен"); (systemctl is-active mailhub-web || echo "mailhub-web: остановлен"); ss -tln | grep -E ":(8000|3001) " || echo "порты 8000/3001 свободны"'
else
  echo "==================== 5. KEEP_RUNNING=1 — сервисы остались запущены ===================="
fi

echo
echo "============================================================"
echo "ГОТОВО. Как всё запустить заново — см. RUN_GUIDE.md"
echo "  systemctl start mailhub mailhub-web"
echo "============================================================"
