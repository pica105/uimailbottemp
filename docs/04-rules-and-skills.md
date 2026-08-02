# Правила и конвенции разработки

## Мультиагентный подход (Freebuff/Buffy)

- **Главный агент (Buffy):** оркестрация, решения, делегирование
- **Суб-агенты:** `file-picker` (поиск файлов), `code-searcher` (ripgrep), `basher` (shell/SSH), `code-reviewer-glm` (ревью изменений), `researcher-web` / `researcher-docs` (веб/доки), `browser-use` (UI-тесты в Chrome), `tmux-cli` (CLI-тесты)
- **Принципы:** параллельное делегирование, минимум изменений, проверка типов/тестов после правок, ревью через code-reviewer, коммиты на GitHub после каждой завершённой фичи

## Стек и кодстайл

### Python (mailhub/)
- Типизация: аннотации обязательны (`from __future__ import annotations`)
- Асинхронность: `asyncio` + `await`; HTTP — aiohttp; БД — aiosqlite; IMAP — aioimaplib
- Конфиг: pydantic-settings, `.env` рядом с пакетом (`mailhub/.env`)
- Логирование: `logging` через `__name__`
- Логика движка: один процесс, без блокирующих вызовов (запрет google-api-python-client — блокирующий SDK)
- Шифрование токенов: Fernet, ключ только в env

### TypeScript/Frontend (mailhub-webapp/)
- TypeScript strict, функциональные компоненты, Tailwind v4 + shadcn/ui
- Данные: TanStack Query + Zustand + Zod-схемы на каждый ответ API
- ESLint + Prettier
- Изменение экспортируемых символов → обновить все импорты (code-searcher)

## VPS-правила (91.186.211.218)

- **Бекенд** = systemd `mailhub` (бот + API :8000 + движок синка), **фронт** = systemd `mailhub-web` (Next.js :3001), **nginx** = `uimail.synergyflow.ru`
- Диск 1 ГБ: пересборка фронта только экономно (кэш npm в `/dev/shm`, `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`, `npm prune --omit=dev`); при дефиците места: `apt-get clean`, `journalctl --vacuum-size=20M`
- Мониторинг: `df -h /`, `free -m`, `journalctl -u mailhub -f`
- ОЗУ ~700 МБ — лимит памяти сборки `NODE_OPTIONS=--max-old-space-size=512`
- Миграции схемы SQLite: CHECK-ограничения меняются только пересозданием таблицы (копирование данных, `PRAGMA foreign_keys=OFF`)
- Деплой: `git pull` на VPS → `systemctl restart mailhub`; фронт требует пересборки

## Тестирование

- Бекенд: `scripts/smoke_test.py` (все проверки) + `scripts/api_simulation.py` (живой HTTP) — обязательно перед пушем
- Фронт: `npm run typecheck`, `npm run test`, при изменении UI — `npm run lint`
- Живые проверки на VPS: реальные письма (mark-read), темп синхронизации (два снапшота `next_sync_at`)

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
