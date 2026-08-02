# MailHub Frontend (Telegram Mini App)

## Стек

- **Фреймворк:** Next.js 16 (App Router), React 19
- **Стили:** Tailwind v4, shadcn/ui (Radix-примитивы), CSS-переменные темы Telegram
- **Данные:** TanStack Query v5, Zustand (стор приложения), Zod (валидация ответов API)
- **i18n:** самописный модуль `lib/i18n.ts`, словари `locales/{en,ru}.json`
- **Тесты:** Vitest (unit), Playwright (e2e), TypeScript strict

## Структура

```
mailhub-webapp/
├── app/
│   ├── page.tsx                 # корень: 307 → /inbox
│   ├── (app)/inbox/page.tsx     # список писем, табы категорий, аккаунты
│   ├── (app)/message/[id]/      # просмотр письма
│   ├── (app)/settings/page.tsx  # язык, интервал, приглушённые категории, аккаунты
│   └── layout.tsx               # провайдеры, тема
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
- **Settings** — язык, интервал синхронизации (10с–30мин), muted-категории, подключённые аккаунты

## Telegram WebApp

- `lib/telegram.ts` — обёртка `window.Telegram.WebApp`: initData, тема (light/dark), BackButton, HapticFeedback, ready/expand
- Аутентификация: `initData` → заголовок `X-Telegram-Init-Data` на каждый запрос API
- Вне Telegram — заглушка «откройте из Telegram» (по задумке)

## API-слой

`lib/api.ts`: типизированные обёртки (zod-схемы ответов), TanStack Query кэширует списки (staleTime 30 с), `useMessages` — мутации mark-read с optimistic update (откат при ошибке). Полинга нет: данные обновляются при навигации и после действий.

## Сборка и деплой

```bash
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8080
npm run dev                        # dev: http://localhost:3000
npm run build && npm start         # prod
```

Прод на VPS: `next build` → systemd `mailhub-web` → `next start -p 3001`, nginx `/` → 3001.

**Экономная сборка на диске 1 ГБ:**

```bash
export NPM_CONFIG_CACHE=/dev/shm/npm-cache     # кэш в RAM, не на диск
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1      # без ~400 МБ браузеров
npm install --no-audit --no-fund
NODE_OPTIONS=--max-old-space-size=512 npm run build
npm prune --omit=dev                           # убрать dev-зависимости после сборки
```

## Тесты

```bash
npm run test          # Vitest (unit: i18n, telegram-обёртка)
npm run typecheck     # tsc --noEmit
npm run lint
npm run test:e2e      # Playwright (нужен: npx playwright install chromium)
```
