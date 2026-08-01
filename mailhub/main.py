"""MailHub entry point.

Launches three concurrent coroutines in a single asyncio process:
  1. aiogram bot (polling)
  2. aiohttp server (OAuth callbacks + Mini App API)
  3. background mail sync loop

Usage (from the project root):
    python mailhub/main.py
    # or
    python -m mailhub.main
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Support `python mailhub/main.py`: this module is not part of the package
# when executed directly, so put the repo root on sys.path and re-enter the
# module as mailhub.main (where relative imports work).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mailhub.main import main

    raise SystemExit(asyncio.run(main()))

import logging
import signal
from contextlib import suppress

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from .bot_handlers import register_handlers
from .config import settings
from .database import Database
from .oauth_server import create_app
from .sync_engine import sync_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("mailhub")


async def main() -> None:
    db = Database()
    await db.connect()
    logger.info("Database ready at %s", settings.DB_PATH)

    stop_event = asyncio.Event()

    def _shutdown() -> None:
        logger.info("Shutdown signal received, stopping...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _shutdown)

    # One shared Bot instance for the poller, the API server, and sync
    # notifications. Closed once at shutdown.
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    router = Router()
    register_handlers(router, db)
    dp = Dispatcher()
    dp.include_router(router)
    dp["db"] = db

    await bot.set_my_commands(
        [
            {"command": "start", "description": "Start / connect account"},
            {"command": "accounts", "description": "Manage accounts"},
            {"command": "settings", "description": "Open settings"},
            {"command": "help", "description": "Help"},
        ]
    )

    server_app = create_app(db, bot)
    runner = web.AppRunner(server_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.HOST, settings.PORT)
    await site.start()
    logger.info("HTTP server listening on http://%s:%s", settings.HOST, settings.PORT)

    tasks = [
        asyncio.create_task(dp.start_polling(bot, handle_signals=False), name="bot"),
        asyncio.create_task(sync_loop(db, bot, stop_event), name="sync"),
    ]

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Shutting down gracefully...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await bot.session.close()
        await runner.cleanup()
        await db.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
