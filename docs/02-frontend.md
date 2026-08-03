# MailHub Frontend (Telegram Mini App)

## Стек

- **Фреймворк:** Next.js 16 (App Router), React 19
- **Стили:** Tailwind v4, shadcn/ui (Radix-примитивы), CSS-переменные темы Telegram
- **Данные:** TanStack Query v5, Zustand (стор приложения), Zod (валидация ответов API)
- **Telegram:** официальный `telegram-web-app.js`, подключённый через `next/script` с `strategy="beforeInteractive"`
- **i18n:** самописный модуль `lib/i18n.ts`, словари `locales/{en,ru}.json`
- **Тесты:** Vitest (unit), Playwright (e2e), TypeScript strict

## Структура

```
mailhub-webapp/
├── app/
│   ├── page.tsx                 # корень: 307 → /inbox
│   ├── (app)/inbox/page.tsx     # список писем, табы категорий, аккаунты
│   ├── (app)/message/[id]/      # просмотр письма
│   ├── (app)/settings/page.tsx  # язык, авто-интервал, muted-категории, аккаунты
│   └── layout.tsx               # Telegram SDK, провайдеры, тема
├── components/                  # ui (shadcn), layout, mail, settings
├── hooks/                       # useTelegram, useAuth, useMessages
├── lib/                         # api.ts (fetch + zod), telegram.ts, i18n.ts
├── stores/                      # appStore.ts (Zustand)
└── tests/                       # vitest/ + e2e/
```

## Роуты и навигация

- `/` → серверный редирект на `/inbox`
- **Inbox** — список писем, табы All / Important / Promo / Spam, переключение аккаунтов, живой статус прочитанного (оптимистичный mark-read + откат при ошибке)
- **Message** — отправитель, тема, тело, кнопка «прочитано» (синхронизируется с ящиком)
- **Settings** — язык и muted-категории. Интервал синхронизации показывается как информация: **автоматически, 10 секунд–5 минут**. Пользователь не может выбрать или сохранить собственный интервал.

## Telegram WebApp и авторизация

### Как появляется initData

`app/layout.tsx` подключает официальный SDK:

```html
<script src="https://telegram.org/js/telegram-web-app.js?1"></script>
```

Скрипт загружается до интерактивного кода Next.js. `hooks/useTelegram.ts` затем:

1. вызывает `Telegram.WebApp.ready()` и `expand()`;
2. применяет тему Telegram;
3. читает `Telegram.WebApp.initData`;
4. повторно проверяет состояние через 0, 50, 250 и 1000 мс — Telegram Web может завершить инициализацию чуть позже;
5. извлекает Telegram user ID только для разделения локального query-кэша.

`lib/api.ts` передаёт исходную подписанную строку в заголовке каждого защищённого запроса:

```text
X-Telegram-Init-Data: <signed initData>
```

Backend проверяет HMAC-SHA256 и срок действия `auth_date`. Сам `initData` нельзя логировать или сохранять в localStorage: это подписанные пользовательские данные с bearer-подобными свойствами.

### Разные устройства и клиенты

Каждое открытие Mini App из Telegram получает собственный `initData`. React Query использует Telegram user ID в ключах `accounts`, `settings`, `messages` и `message`, поэтому кэш одного Telegram-пользователя не переиспользуется для другого пользователя в том же WebView.

Если Telegram SDK не появился или Mini App открыт обычным браузером, защищённые queries не запускаются. Вместо ложного состояния «аккаунты не подключены» приложение показывает «Откройте MailHub в Telegram».

Если в backend-логе появляется `Mini App auth rejected`, проверяйте:

```bash
journalctl -u mailhub --since '15 min ago' --no-pager \
  | grep -E 'Mini App auth rejected|aiohttp.access.*api/'
```

Лог содержит только метод, path, наличие `initData`, ограниченный User-Agent и path-only Referer. Полная строка `initData` туда не попадает.

## API-слой

`lib/api.ts`: типизированные обёртки (Zod-схемы ответов). `accounts` и `settings` имеют `staleTime: 30 с`; список сообщений использует общий `QueryClient`-параметр `staleTime: 15 с`. `useMessages` содержит мутации mark-read с optimistic update и откатом при ошибке. Полинга во frontend нет: данные обновляются при загрузке, навигации, ручном refresh и после действий.

Защищённые queries включаются только при наличии `initData`. `/api/health` — единственный публичный health-check; остальные `/api/*` требуют валидную Telegram-подпись.

## Сборка и деплой

```bash
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8080
npm run dev                          # dev: http://localhost:3000
npm run build && npm start           # prod
```

Прод на VPS: `next build` → systemd `mailhub-web` → `next start -p 3001`, nginx `/` → 3001.

**Экономная сборка при тесном диске:** сначала проверьте `df -h /`. Если dev-зависимости уже установлены, повторный install не нужен. При необходимости восстановления зависимостей сначала убедитесь, что свободного места достаточно, затем направьте кэш npm в RAM:

```bash
df -h /
export NPM_CONFIG_CACHE=/dev/shm/npm-cache
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export NEXT_TELEMETRY_DISABLED=1
export NODE_OPTIONS=--max-old-space-size=512
npm install --include=dev --no-audit --no-fund
npm run build
rm -rf /dev/shm/npm-cache /tmp/npm-cache
```

Не запускайте `npm prune --omit=dev` до завершения всех сборок и тестов: он удаляет Tailwind/PostCSS/TypeScript и последующая сборка упадёт. Если dev-зависимости уже установлены, для повторной сборки достаточно `npm run build`.

## Тесты

```bash
npm run test          # Vitest
npm run typecheck     # tsc --noEmit
npm run lint
npm run test:e2e      # Playwright (нужен: npx playwright install chromium)
```

E2E-покрытие должно проверять не только наличие SDK `<script>`, но и отправку `X-Telegram-Init-Data` в `/api/*`. Для внешней проверки домена из локального компьютера используется:

```bash
./.venv/bin/python scripts/external_api_test.py
```

Скрипт проверяет health, ожидаемый `401` без initData, авторизованные accounts/settings/messages/mark-read и сохранение настроек через публичный HTTPS-домен.
