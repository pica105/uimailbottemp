"""All aiogram 3.x handlers, keyboards, and the i18n helper.

Implements: /start with language selection, account connection flow,
/accounts management, /settings, /help, and the notification sender used
by the sync engine.
"""

from __future__ import annotations

import json
import logging
import secrets
from html import escape
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .config import settings
from .database import Database
from .mark_read import spawn_mark_read

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).resolve().parent / "locales"


class I18n:
    """Tiny JSON-based translator. Keys are resolved per language with
    str.format() interpolation for placeholders like {email}."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, str]] = {}
        for lang in ("en", "ru"):
            path = LOCALES_DIR / f"{lang}.json"
            self._data[lang] = json.loads(path.read_text(encoding="utf-8"))

    def t(self, lang: str, key: str, **kwargs: Any) -> str:
        table = self._data.get(lang) or self._data["en"]
        template = table.get(key, key)
        return template.format(**kwargs) if kwargs else template


i18n = I18n()


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------
def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🇷🇺 Русский", callback_data="lang:ru")
    builder.button(text="🇬🇧 English", callback_data="lang:en")
    builder.adjust(2)
    return builder.as_markup()


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(lang, "btn_connect"), callback_data="connect:start")
    builder.button(text=i18n.t(lang, "btn_settings"), callback_data="settings:open")
    builder.button(text=i18n.t(lang, "btn_help"), callback_data="help:open")
    builder.adjust(1)
    return builder.as_markup()


def provider_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(lang, "provider_gmail"), callback_data="provider:gmail")
    builder.button(text=i18n.t(lang, "provider_yandex"), callback_data="provider:yandex")
    builder.button(text=i18n.t(lang, "btn_back"), callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def auth_link_keyboard(auth_url: str, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(lang, "authorize"), url=auth_url)
    return builder.as_markup()


def accounts_keyboard(accounts: list[dict], lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for acc in accounts:
        icon = "📧"
        label = f"{icon} {acc['email']}"
        builder.button(
            text=label, callback_data=f"account:manage:{acc['id']}"
        )
    builder.button(text=i18n.t(lang, "btn_connect"), callback_data="connect:start")
    builder.button(text=i18n.t(lang, "btn_back"), callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def confirm_unlink_keyboard(account_id: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ " + i18n.t(lang, "btn_unlink"),
        callback_data=f"account:unlink_confirm:{account_id}",
    )
    builder.button(text=i18n.t(lang, "btn_cancel"), callback_data=f"account:manage:{account_id}")
    builder.adjust(2)
    return builder.as_markup()


def settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.t(lang, "open_mini_app"),
        web_app=WebAppInfo(url=settings.MINI_APP_URL),
    )
    builder.button(text=i18n.t(lang, "btn_back"), callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


# ---------------------------------------------------------------------------
# OAuth URL builders (shared with oauth_server)
# ---------------------------------------------------------------------------
def build_oauth_url(provider: str, state: str) -> str:
    base = settings.BASE_URL.rstrip("/")
    redirect_uri = f"{base}/oauth/{provider}/callback"
    if provider == "gmail":
        return (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={settings.GOOGLE_CLIENT_ID}"
            "&response_type=code"
            # gmail.modify is needed to remove the UNREAD label when the
            # user marks a message read (readonly cannot write).
            "&scope=https://www.googleapis.com/auth/gmail.modify"
            "&access_type=offline&prompt=consent"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
        )
    if provider == "yandex":
        return (
            "https://oauth.yandex.ru/authorize"
            f"?client_id={settings.YANDEX_CLIENT_ID}"
            "&response_type=code"
            "&scope=login:email%20mail:imap_full"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
        )
    raise ValueError(f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def register_handlers(router: Router, db: Database) -> None:
    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        user = await db.get_or_create_user(
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        if user["language"] not in ("ru", "en"):
            await message.answer(
                i18n.t("en", "choose_language"),
                reply_markup=language_keyboard(),
            )
            return
        lang = user["language"]
        await message.answer(
            i18n.t(lang, "welcome"),
            reply_markup=main_menu_keyboard(lang),
        )

    @router.callback_query(F.data == "lang:ru")
    async def on_lang_ru(call: CallbackQuery) -> None:
        await db.set_language(call.from_user.id, "ru")
        await call.message.edit_text(
            i18n.t("ru", "welcome"),
            reply_markup=main_menu_keyboard("ru"),
        )
        await call.answer()

    @router.callback_query(F.data == "lang:en")
    async def on_lang_en(call: CallbackQuery) -> None:
        await db.set_language(call.from_user.id, "en")
        await call.message.edit_text(
            i18n.t("en", "welcome"),
            reply_markup=main_menu_keyboard("en"),
        )
        await call.answer()

    @router.callback_query(F.data == "menu:main")
    async def on_menu_main(call: CallbackQuery) -> None:
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        await call.message.edit_text(
            i18n.t(lang, "main_menu"),
            reply_markup=main_menu_keyboard(lang),
        )
        await call.answer()

    @router.callback_query(F.data == "connect:start")
    async def on_connect_start(call: CallbackQuery) -> None:
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        await call.message.edit_text(
            i18n.t(lang, "choose_provider"),
            reply_markup=provider_keyboard(lang),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("provider:"))
    async def on_provider(call: CallbackQuery) -> None:
        provider = call.data.split(":", 1)[1]
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        state = secrets.token_urlsafe(32)
        await db.save_oauth_state(state, call.from_user.id, provider)
        auth_url = build_oauth_url(provider, state)
        await call.message.edit_text(
            i18n.t(lang, "auth_instructions"),
            reply_markup=auth_link_keyboard(auth_url, lang),
        )
        await call.answer()

    @router.callback_query(F.data == "settings:open")
    async def on_settings_open(call: CallbackQuery) -> None:
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        await call.message.edit_text(
            i18n.t(lang, "settings_hint"),
            reply_markup=settings_keyboard(lang),
        )
        await call.answer()

    @router.callback_query(F.data == "help:open")
    async def on_help_open(call: CallbackQuery) -> None:
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        await call.message.edit_text(
            i18n.t(lang, "help"), parse_mode="HTML"
        )
        await call.answer()

    @router.message(Command("accounts"))
    async def cmd_accounts(message: Message) -> None:
        user = await db.get_user(message.from_user.id)
        lang = (user or {}).get("language", "en")
        accounts = await db.get_accounts(message.from_user.id)
        if not accounts:
            await message.answer(
                i18n.t(lang, "no_accounts"),
                reply_markup=main_menu_keyboard(lang),
            )
            return
        text = i18n.t(lang, "accounts_title") + "\n"
        for acc in accounts:
            icon = "📧"
            if acc["is_active"]:
                status = i18n.t(lang, "status_active")
            elif acc["sync_error_count"] > 0:
                status = i18n.t(lang, "status_error", count=acc["sync_error_count"])
            else:
                status = i18n.t(lang, "status_inactive")
            text += "\n" + i18n.t(
                lang, "account_list_item", provider_icon=icon,
                email=acc["email"], status=status,
            )
        await message.answer(text, reply_markup=accounts_keyboard(accounts, lang))

    @router.callback_query(F.data == "accounts:list")
    async def on_accounts_list(call: CallbackQuery) -> None:
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        accounts = await db.get_accounts(call.from_user.id)
        if not accounts:
            await call.message.edit_text(
                i18n.t(lang, "no_accounts"),
                reply_markup=main_menu_keyboard(lang),
            )
            await call.answer()
            return
        text = i18n.t(lang, "accounts_title")
        await call.message.edit_text(
            text, reply_markup=accounts_keyboard(accounts, lang)
        )
        await call.answer()

    @router.callback_query(F.data.startswith("account:manage:"))
    async def on_account_manage(call: CallbackQuery) -> None:
        account_id = int(call.data.split(":")[2])
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        account = await db.get_account(account_id)
        if account is None:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        await call.message.edit_text(
            i18n.t(lang, "confirm_unlink", email=account["email"]),
            reply_markup=confirm_unlink_keyboard(account_id, lang),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("account:unlink_confirm:"))
    async def on_account_unlink(call: CallbackQuery) -> None:
        account_id = int(call.data.split(":")[2])
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        account = await db.get_account(account_id)
        if account is None:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        email = account["email"]
        await db.delete_account(account_id)
        await call.message.edit_text(
            i18n.t(lang, "account_disconnected", email=email),
            reply_markup=main_menu_keyboard(lang),
        )
        await call.answer(i18n.t(lang, "account_disconnected", email=email))

    @router.message(Command("settings"))
    async def cmd_settings(message: Message) -> None:
        user = await db.get_user(message.from_user.id)
        lang = (user or {}).get("language", "en")
        await message.answer(
            i18n.t(lang, "settings_hint"),
            reply_markup=settings_keyboard(lang),
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        user = await db.get_user(message.from_user.id)
        lang = (user or {}).get("language", "en")
        await message.answer(i18n.t(lang, "help"), parse_mode="HTML")

    @router.callback_query(F.data.startswith("msg:read:"))
    async def on_msg_read(call: CallbackQuery) -> None:
        message_id = int(call.data.split(":")[2])
        msg = await db.get_message(message_id)
        if msg is None:
            await call.answer(i18n.t("en", "error_generic"))
            return
        await db.mark_read(message_id)
        spawn_mark_read(db, msg["account_id"], msg["provider_message_id"])
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        await call.answer(i18n.t(lang, "marked_read"))


# ---------------------------------------------------------------------------
# Notification sender (used by the sync engine)
# ---------------------------------------------------------------------------
async def send_new_mail_notification(
    bot: Bot,
    db: Database,
    telegram_id: int,
    lang: str,
    message: dict,
) -> None:
    """Send a Telegram notification for a newly synced message."""
    category_key = f"category_{message['category']}"
    title = i18n.t(lang, "new_email_title", category=i18n.t(lang, category_key))
    sender = escape(message.get("sender_name") or message.get("sender_email") or "?")
    subject = escape(message.get("subject") or "(no subject)")
    snippet = escape((message.get("snippet") or message.get("body_text") or "")[:200])

    text = (
        f"{title}\n\n"
        f"<b>{i18n.t(lang, 'notification_from')}</b> {sender}\n"
        f"<b>{i18n.t(lang, 'notification_subject')}</b> {subject}\n\n"
        f"<i>{snippet}</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.t(lang, "btn_open_in_app"),
        web_app=WebAppInfo(url=f"{settings.MINI_APP_URL}/message/{message['id']}"),
    )
    builder.button(
        text=i18n.t(lang, "btn_mark_read"),
        callback_data=f"msg:read:{message['id']}",
    )
    builder.adjust(1)

    try:
        await bot.send_message(
            telegram_id,
            text,
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
        await db.mark_notified(message["id"])
    except Exception:  # noqa: BLE001 - notify failure must not break sync
        logger.exception("Failed to send notification for message %s", message["id"])
