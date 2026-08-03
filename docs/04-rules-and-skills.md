# Правила и конвенции разработки

> ⚠️ **Обязательная техника работы — см. `docs/05-multiagent-workflow.md`.**
> Разбивать задачи на макро/микро, для каждой микро-задачи: независимые
> агенты-подходы → отбор лучшего → интеграция → тест → ревью → симуляция
> пользователя → итерация при багах. Работать так **всегда**.

## Мультиагентный подход (Freebuff/Buffy)

- **Главный агент (Buffy):** оркестрация, решения, делегирование
- **Суб-агенты:** `file-picker` (поиск файлов), `code-searcher` (ripgrep), `basher` (shell/SSH), доступный `code-reviewer` (ревью изменений), `researcher-web` / `researcher-docs` (веб/доки), `browser-use` (UI-тесты в Chrome), `tmux-cli` (CLI-тесты)
- **Принципы:** параллельное делегирование, минимум изменений, проверка типов/тестов после правок, ревью через code-reviewer, коммиты на GitHub после каждой завершённой фичи

## Стек и кодстайл

### Python (mailhub/)
- Типизация: аннотации обязательны (`from __future__ import annotations`)
- Асинхронность: `asyncio` + `await`; HTTP — aiohttp; БД — aiosqlite; IMAP — aioimaplib
- Конфиг: pydantic-settings, `.env` рядом с пакетом (`mailhub/.env`)
- Логирование: `logging` через `__name__`
- Логика движка: один процесс, без блокирующих вызовов (запрет google-api-python-client — блокирующий SDK)
- Шифрование токенов: Fernet, ключ только в env
- Не логировать `initData`, OAuth-коды, access/refresh tokens и содержимое писем

### TypeScript/Frontend (mailhub-webapp/)
- TypeScript strict, функциональные компоненты, Tailwind v4 + shadcn/ui
- Данные: TanStack Query + Zustand + Zod-схемы на каждый ответ API
- Telegram SDK подключается в root layout через `next/script` с `beforeInteractive`
- Protected queries запускаются только при наличии Telegram `initData`
- Query keys должны учитывать Telegram user ID; initData нельзя класть в query key или localStorage
- ESLint + Prettier
- Изменение экспортируемых символов → обновить все импорты (code-searcher)

## VPS-правила (91.186.211.218)

- **Бекенд** = systemd `mailhub` (бот + API :8000 + движок синка), **фронт** = systemd `mailhub-web` (Next.js :3001), **nginx** = `uimail.synergyflow.ru`
- Диск мал: перед операцией `df -h /`; кэш npm направлять в `/dev/shm/npm-cache`; Playwright browsers на VPS не скачивать
- Не запускать `npm prune --omit=dev` до завершения сборки и тестов: он удаляет Tailwind/PostCSS/TypeScript и ломает следующую сборку
- После восстановления dev-зависимостей сначала проверить свободное место: VPS может снова заполниться; не делать повторный `npm install` без необходимости
- ОЗУ ограничено — `NODE_OPTIONS=--max-old-space-size=512`
- При деплое не трогать `.env`, `mailhub.db` и `venv/`; проверить `git status` перед `git pull --ff-only`
- После `systemctl restart` ждать реального ответа `/api/health`, а не полагаться на фиксированный `sleep`: backend сначала подключается к Telegram API
- Миграции схемы SQLite: CHECK-ограничения меняются только пересозданием таблицы (копирование данных, `PRAGMA foreign_keys=OFF`)
- Если Git показывает локальный `package-lock.json` после npm install — проверить diff и восстановить только этот служебный файл перед pull, если он не содержит намеренных изменений

## Протокол диагностики Telegram Mini App

1. Проверить nginx access/error и backend journal за один временной интервал.
2. Сопоставить `Referer`, User-Agent, маршрут страницы и API-ответы.
3. Проверить наличие SDK в production HTML:

   ```bash
   curl -sk https://uimail.synergyflow.ru/inbox \
     | grep -o 'https://telegram.org/js/telegram-web-app.js[^" ]*'
   ```

4. Убедиться, что запрос без initData получает ожидаемый 401, а запрос с валидной подписью получает 200.
5. Проверить, что при отсутствии SDK frontend не показывает ложные данные и не запускает защищённые queries.
6. Для разных устройств не сравнивать User-Agent как доказательство авторизации: Telegram Web/Desktop могут использовать браузерный User-Agent. Источник истины — наличие и валидность `X-Telegram-Init-Data`.
7. Не печатать initData в логи, отчёты, screenshots или тестовые артефакты.

## Тестирование

- Backend: `scripts/smoke_test.py` + `scripts/api_simulation.py` — обязательно перед пушем
- Frontend: `npm run typecheck`, `npm run test`, `npm run lint`, `npm run build`
- E2E: наличие Telegram SDK и фактический `X-Telegram-Init-Data` в API-запросе
- Внешний домен: `scripts/external_api_test.py` с валидной подписью и проверкой ожидаемого 401 без неё
- Живые проверки на VPS: реальные письма (mark-read), темп синхронизации, `/api/health`, nginx → backend/frontend, отсутствие неожиданных 401/403/5xx

## Деплой

1. `git status` локально и на VPS; не затирать `.env`, БД и venv.
2. `git pull --ff-only`.
3. Backend: `py_compile`, затем `systemctl restart mailhub`.
4. Frontend: экономная `npm run build`, затем `systemctl restart mailhub-web`.
5. Дождаться health 200 polling loop.
6. Проверить прямые порты, nginx localhost и публичный домен.
7. Проверить journal на auth/API/sync ошибки.
8. Только после этого считать деплой завершённым.

Для простой docs-only правки без изменения поведения допускается облегчённый режим: контекст → редактура → текстовый факт-чек → ревью diff. Полный цикл с большим числом агентских микро-задач обязателен для кода, инфраструктуры и пользовательских изменений поведения.

## Полезные скиллы

| Скилл | Назначение |
|---|---|
| `ui-ux-pro-max` / `frontend-design` | Дизайн-решения, production UI |
| `accessibility` | WCAG 2.1 |
| `react-best-practices` | Performance-паттерны React/Next.js |
| `core-web-vitals` | LCP/INP/CLS |
| `api-design` | REST API |
| `security-review` | Аудит безопасности |
| `testing` / `tdd` | Тесты |
| `commit` / `caveman-commit` | Коммиты (Conventional Commits) |
| `caveman` | Сжатый стиль коммуникации |
