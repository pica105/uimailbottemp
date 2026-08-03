"""All aiogram 3.x handlers, keyboards, and the i18n helper.

Implements: /start with inline language selection, account connection flow,
/accounts management, /settings (language + muted categories), /help, and
the notification sender used by the sync engine (rich HTML body, optional
photo, expandable preview, and inline actions).
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
    KeyboardButton,
    LinkPreviewOptions,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .config import settings
from .database import Database
from .html_email import body_to_segments, render_segments, visible_len
from .mark_read import spawn_delete_provider, spawn_mark_read

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

# Notification preview length: longer bodies are collapsed behind "↓ more".
MAX_PREVIEW_CHARS = 250


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
    builder.button(text=i18n.t("ru", "lang_name_ru"), callback_data="lang:ru")
    builder.button(text=i18n.t("en", "lang_name_en"), callback_data="lang:en")
    builder.adjust(2)
    return builder.as_markup()


def main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Persistent root navigation; actions below remain contextual inline buttons."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=i18n.t(lang, "btn_accounts"))],
            [
                KeyboardButton(text=i18n.t(lang, "btn_connect")),
                KeyboardButton(text=i18n.t(lang, "btn_settings")),
            ],
            [KeyboardButton(text=i18n.t(lang, "btn_help"))],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=i18n.t(lang, "input_placeholder"),
    )


def provider_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Account-adding menu. Deliberately has no Back button: the persistent
    reply keyboard below already provides root navigation."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(lang, "provider_gmail"), callback_data="provider:gmail")
    builder.button(text=i18n.t(lang, "provider_yandex"), callback_data="provider:yandex")
    builder.adjust(2)
    return builder.as_markup()


def auth_link_keyboard(auth_url: str, lang: str) -> InlineKeyboardMarkup:
    """OAuth link screen; Back returns to the account-adding menu."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(lang, "authorize"), url=auth_url)
    builder.button(text=i18n.t(lang, "btn_back"), callback_data="connect:start")
    builder.adjust(1)
    return builder.as_markup()


def connect_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Empty-accounts state: a single button that opens the adding menu,
    exactly like pressing 'Connect' in the reply keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(lang, "btn_connect"), callback_data="connect:start")
    builder.adjust(1)
    return builder.as_markup()


def accounts_keyboard(accounts: list[dict], lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for acc in accounts:
        builder.button(
            text=acc["email"], callback_data=f"account:manage:{acc['id']}"
        )
    builder.button(text=i18n.t(lang, "btn_connect"), callback_data="connect:start")
    builder.button(text=i18n.t(lang, "btn_back"), callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def confirm_unlink_keyboard(account_id: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.t(lang, "btn_unlink"),
        callback_data=f"account:unlink_confirm:{account_id}",
    )
    builder.button(text=i18n.t(lang, "btn_cancel"), callback_data=f"account:manage:{account_id}")
    builder.adjust(2)
    return builder.as_markup()


def settings_keyboard(
    lang: str, muted: list[str], categories: list[str]
) -> InlineKeyboardMarkup:
    """Settings live in the bot: language (✓ = active) and per-category
    mute toggles, plus a link to the Mini App."""
    builder = InlineKeyboardBuilder()
    ru_label = ("✓ " if lang == "ru" else "") + i18n.t("ru", "lang_name_ru")
    en_label = ("✓ " if lang == "en" else "") + i18n.t("en", "lang_name_en")
    builder.button(text=ru_label, callback_data="settings:lang:ru")
    builder.button(text=en_label, callback_data="settings:lang:en")
    for cat in categories:
        checked = cat in muted
        label = f"{'✓ ' if checked else ''}{i18n.t(lang, f'category_{cat}')}"
        builder.button(text=label, callback_data=f"settings:mute:{cat}")
    builder.button(
        text=i18n.t(lang, "open_mini_app"),
        web_app=WebAppInfo(url=settings.MINI_APP_URL),
    )
    builder.adjust(2, *([1] * len(categories)), 1)
    return builder.as_markup()


def configure_menu_button(lang: str = "en") -> MenuButtonWebApp:
    """Build the persistent private-chat button that opens the Mini App."""
    return MenuButtonWebApp(
        text=i18n.t(lang, "open_mini_app_menu"),
        web_app=WebAppInfo(url=settings.MINI_APP_URL),
    )


# ---------------------------------------------------------------------------
# Notification builders
# ---------------------------------------------------------------------------
def build_notification(message: dict) -> tuple[str, str | None, bool]:
    """Return (html_text, first_image_url, was_truncated).

    Text layout follows the product example: the header is plain (envelope +
    raw sender line + subject), the body keeps its line structure with
    hyperlinks inline and bare URLs shortened.
    """
    sender_name = message.get("sender_name") or ""
    sender_email = message.get("sender_email") or ""
    if sender_name and sender_email:
        sender_line = f"{sender_name} <{sender_email}>"
    else:
        sender_line = sender_name or sender_email or "?"
    subject = message.get("subject") or "(no subject)"
    header = f"✉️ {escape(sender_line)}\n{escape(subject)}\n\n"
    header_len = len(header)

    segments, images = body_to_segments(
        message.get("body_html"),
        message.get("body_text") or message.get("snippet") or "",
    )
    image = next((u for u in images if u.startswith(("https://", "http://"))), None)
    full_body = render_segments(segments, None)
    truncated = header_len + visible_len(full_body) > MAX_PREVIEW_CHARS
    if truncated:
        body = render_segments(segments, max(20, MAX_PREVIEW_CHARS - header_len))
    else:
        body = full_body
    return header + body, image, truncated


def notification_keyboard(
    message_id: int,
    lang: str,
    provider: str,
    *,
    truncated: bool = False,
    expanded: bool = False,
    actions: bool = False,
    sender_email: str | None = None,
    provider_message_id: str | None = None,
) -> InlineKeyboardMarkup:
    """Inline keyboard for a mail notification.

    Normal:        [Открыть, Действия →]
    Long preview:  [↓ больше | Действия →]  then  [Открыть]
    Expanded:      [↑ меньше | Действия →]  then  [Открыть]
    Actions:       [скрыть письма от EMAIL]  [открыть в gmail/Япочте]
                   [←, 👁️🗨️, 🗑️]
    """
    builder = InlineKeyboardBuilder()
    if actions:
        email = (sender_email or "?").upper()
        builder.button(
            text=i18n.t(lang, "btn_hide_from", email=email),
            callback_data=f"msg:hide:{message_id}",
        )
        if provider == "gmail":
            builder.button(
                text=i18n.t(lang, "btn_open_gmail"),
                url=f"https://mail.google.com/mail/u/0/#all/{provider_message_id or ''}",
            )
        else:
            builder.button(
                text=i18n.t(lang, "btn_open_yandex"),
                url="https://mail.yandex.ru/",
            )
        builder.button(text=i18n.t(lang, "btn_back_arrow"), callback_data=f"msg:back:{message_id}")
        builder.button(text=i18n.t(lang, "btn_mark_read_eye"), callback_data=f"msg:read:{message_id}")
        builder.button(text=i18n.t(lang, "btn_delete_trash"), callback_data=f"msg:delete:{message_id}")
        builder.adjust(1, 1, 3)
        return builder.as_markup()

    if truncated or expanded:
        builder.button(
            text=i18n.t(lang, "btn_less" if expanded else "btn_more"),
            callback_data=f"msg:{'less' if expanded else 'more'}:{message_id}",
        )
        builder.button(
            text=i18n.t(lang, "btn_actions"), callback_data=f"msg:actions:{message_id}"
        )
        builder.button(
            text=i18n.t(lang, "btn_open"),
            web_app=WebAppInfo(url=f"{settings.MINI_APP_URL}/message/{message_id}"),
        )
        builder.adjust(2, 1)
        return builder.as_markup()

    builder.button(
        text=i18n.t(lang, "btn_open"),
        web_app=WebAppInfo(url=f"{settings.MINI_APP_URL}/message/{message_id}"),
    )
    builder.button(
        text=i18n.t(lang, "btn_actions"), callback_data=f"msg:actions:{message_id}"
    )
    builder.adjust(2)
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
    # --- /start: always ask for the language first -----------------------
    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        await db.get_or_create_user(
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        user = await db.get_user(message.from_user.id)
        lang = (user or {}).get("language", "en")
        await message.bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=configure_menu_button(lang),
        )
        await message.answer(
            i18n.t(lang, "choose_language"),
            reply_markup=language_keyboard(),
        )

    async def _finish_language_selection(call: CallbackQuery, lang: str) -> None:
        await db.set_language(call.from_user.id, lang)
        await call.message.edit_text(i18n.t(lang, "welcome"))
        await call.message.answer(
            i18n.t(lang, "main_menu"),
            reply_markup=main_menu_keyboard(lang),
        )
        await call.bot.set_chat_menu_button(
            chat_id=call.message.chat.id,
            menu_button=configure_menu_button(lang),
        )
        await call.answer()

    @router.callback_query(F.data == "lang:ru")
    async def on_lang_ru(call: CallbackQuery) -> None:
        await _finish_language_selection(call, "ru")

    @router.callback_query(F.data == "lang:en")
    async def on_lang_en(call: CallbackQuery) -> None:
        await _finish_language_selection(call, "en")

    # --- Root navigation -------------------------------------------------
    @router.callback_query(F.data == "menu:main")
    async def on_menu_main(call: CallbackQuery) -> None:
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        # Edit in place only: the persistent reply keyboard is always
        # visible, so resending it would just duplicate the message.
        await call.message.edit_text(i18n.t(lang, "main_menu"))
        await call.answer()

    @router.message(F.text.in_({i18n.t("en", "btn_connect"), i18n.t("ru", "btn_connect")}))
    async def on_connect_message(message: Message) -> None:
        user = await db.get_user(message.from_user.id)
        lang = (user or {}).get("language", "en")
        await message.answer(
            i18n.t(lang, "choose_provider"),
            reply_markup=provider_keyboard(lang),
        )

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
        if provider not in {"gmail", "yandex"}:
            await call.answer(i18n.t("en", "error_generic"), show_alert=True)
            return
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        state = secrets.token_urlsafe(32)
        await db.save_oauth_state(state, call.from_user.id, provider)
        auth_url = build_oauth_url(provider, state)
        await call.message.edit_text(
            i18n.t(lang, "auth_instructions"),
            reply_markup=auth_link_keyboard(auth_url, lang),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await call.answer()

    # --- Settings (language + muted categories, in the bot) --------------
    async def _render_settings_message(target: Message, user_id: int) -> None:
        user = await db.get_user(user_id)
        lang = (user or {}).get("language", "en")
        try:
            muted = json.loads((user or {}).get("muted_categories") or "[]")
        except json.JSONDecodeError:
            muted = []
        categories = await db.get_user_categories(user_id)
        await target.answer(
            i18n.t(lang, "settings_title"),
            reply_markup=settings_keyboard(lang, muted, categories),
        )

    @router.message(F.text.in_({i18n.t("en", "btn_settings"), i18n.t("ru", "btn_settings")}))
    @router.message(Command("settings"))
    async def cmd_settings(message: Message) -> None:
        await _render_settings_message(message, message.from_user.id)

    @router.callback_query(F.data == "settings:open")
    async def on_settings_open(call: CallbackQuery) -> None:
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        try:
            muted = json.loads((user or {}).get("muted_categories") or "[]")
        except json.JSONDecodeError:
            muted = []
        categories = await db.get_user_categories(call.from_user.id)
        await call.message.edit_text(
            i18n.t(lang, "settings_title"),
            reply_markup=settings_keyboard(lang, muted, categories),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("settings:lang:"))
    async def on_settings_lang(call: CallbackQuery) -> None:
        lang = call.data.split(":", 2)[2]
        if lang not in ("ru", "en"):
            await call.answer(i18n.t("en", "error_generic"), show_alert=True)
            return
        await db.set_language(call.from_user.id, lang)
        user = await db.get_user(call.from_user.id)
        try:
            muted = json.loads((user or {}).get("muted_categories") or "[]")
        except json.JSONDecodeError:
            muted = []
        categories = await db.get_user_categories(call.from_user.id)
        await call.message.edit_text(
            i18n.t(lang, "settings_title"),
            reply_markup=settings_keyboard(lang, muted, categories),
        )
        # Refresh the persistent reply keyboard labels to the new language.
        await call.message.answer(
            i18n.t(lang, "language_changed", language=i18n.t(lang, f"lang_name_{lang}")),
            reply_markup=main_menu_keyboard(lang),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("settings:mute:"))
    async def on_settings_mute(call: CallbackQuery) -> None:
        category = call.data.split(":", 2)[2]
        if not category:
            await call.answer(i18n.t("en", "error_generic"), show_alert=True)
            return
        user = await db.get_user(call.from_user.id)
        try:
            muted = json.loads((user or {}).get("muted_categories") or "[]")
        except json.JSONDecodeError:
            muted = []
        if category in muted:
            muted.remove(category)
        else:
            muted.append(category)
        await db.update_settings(call.from_user.id, muted_categories=muted)
        lang = (user or {}).get("language", "en")
        categories = await db.get_user_categories(call.from_user.id)
        await call.message.edit_text(
            i18n.t(lang, "settings_title"),
            reply_markup=settings_keyboard(lang, muted, categories),
        )
        await call.answer()

    # --- Accounts --------------------------------------------------------
    @router.message(F.text.in_({i18n.t("en", "btn_accounts"), i18n.t("ru", "btn_accounts")}))
    @router.message(Command("accounts"))
    async def cmd_accounts(message: Message) -> None:
        user = await db.get_user(message.from_user.id)
        lang = (user or {}).get("language", "en")
        accounts = await db.get_accounts(message.from_user.id)
        if not accounts:
            await message.answer(
                i18n.t(lang, "no_accounts"),
                reply_markup=connect_keyboard(lang),
            )
            return
        text = i18n.t(lang, "accounts_title") + "\n"
        for acc in accounts:
            if acc["is_active"]:
                status = i18n.t(lang, "status_active")
            elif acc["sync_error_count"] > 0:
                status = i18n.t(lang, "status_error", count=acc["sync_error_count"])
            else:
                status = i18n.t(lang, "status_inactive")
            text += "\n" + i18n.t(
                lang, "account_list_item", email=escape(acc["email"]), status=status,
            )
        await message.answer(text, reply_markup=accounts_keyboard(accounts, lang))

    @router.callback_query(F.data == "accounts:list")
    async def on_accounts_list(call: CallbackQuery) -> None:
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        accounts = await db.get_accounts(call.from_user.id)
        if not accounts:
            # Edit in place with a working inline button — no duplicate message.
            await call.message.edit_text(
                i18n.t(lang, "no_accounts"),
                reply_markup=connect_keyboard(lang),
            )
            await call.answer()
            return
        text = i18n.t(lang, "accounts_title")
        await call.message.edit_text(text, reply_markup=accounts_keyboard(accounts, lang))
        await call.answer()

    @router.callback_query(F.data.startswith("account:manage:"))
    async def on_account_manage(call: CallbackQuery) -> None:
        try:
            account_id = int(call.data.split(":", 2)[2])
        except (IndexError, TypeError, ValueError):
            await call.answer(i18n.t("en", "error_generic"), show_alert=True)
            return
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        account = await db.get_account(account_id)
        if account is None or account["user_id"] != call.from_user.id:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        await call.message.edit_text(
            i18n.t(lang, "confirm_unlink", email=escape(account["email"])),
            reply_markup=confirm_unlink_keyboard(account_id, lang),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("account:unlink_confirm:"))
    async def on_account_unlink(call: CallbackQuery) -> None:
        try:
            account_id = int(call.data.split(":", 2)[2])
        except (IndexError, TypeError, ValueError):
            await call.answer(i18n.t("en", "error_generic"), show_alert=True)
            return
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        account = await db.get_account(account_id)
        if account is None or account["user_id"] != call.from_user.id:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        email = account["email"]
        await db.delete_account(account_id, call.from_user.id)
        await call.message.edit_text(
            i18n.t(lang, "account_disconnected", email=escape(email)),
        )
        await call.message.answer(
            i18n.t(lang, "main_menu"),
            reply_markup=main_menu_keyboard(lang),
        )
        await call.answer(i18n.t(lang, "account_disconnected_toast", email=email))

    @router.message(F.text.in_({i18n.t("en", "btn_help"), i18n.t("ru", "btn_help")}))
    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        user = await db.get_user(message.from_user.id)
        lang = (user or {}).get("language", "en")
        await message.answer(i18n.t(lang, "help"), parse_mode="HTML")

    # --- Message actions on notifications --------------------------------
    async def _load_owned_message(call: CallbackQuery) -> tuple[dict | None, dict | None]:
        try:
            message_id = int(call.data.split(":", 2)[2])
        except (IndexError, TypeError, ValueError):
            return None, None
        msg = await db.get_message(message_id)
        account = await db.get_account(msg["account_id"]) if msg else None
        if msg is None or account is None or account["user_id"] != call.from_user.id:
            return None, None
        return msg, account

    async def _edit_text_or_caption(message: Message, text: str, reply_markup) -> None:
        """Edit a notification message in place (text or media caption).

        Failures (e.g. Telegram's "message is not modified" on a duplicate
        tap) are swallowed so the callback still gets answered instead of
        leaving the button spinner stuck.
        """
        try:
            await message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except Exception:  # media message → edit the caption instead
            try:
                await message.edit_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            except Exception:  # noqa: BLE001 - best-effort in-place edit
                logger.debug("Could not edit notification message in place")

    @router.callback_query(F.data.startswith("msg:actions:"))
    async def on_msg_actions(call: CallbackQuery) -> None:
        msg, account = await _load_owned_message(call)
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        if msg is None or account is None:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        text = call.message.text or call.message.caption or ""
        await _edit_text_or_caption(
            call.message,
            text,
            notification_keyboard(
                msg["id"], lang, account["provider"], actions=True,
                sender_email=msg.get("sender_email"),
                provider_message_id=msg.get("provider_message_id"),
            ),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("msg:back:"))
    async def on_msg_back(call: CallbackQuery) -> None:
        msg, account = await _load_owned_message(call)
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        if msg is None or account is None:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        text, _image, truncated = build_notification(msg)
        await _edit_text_or_caption(
            call.message,
            text,
            notification_keyboard(
                msg["id"], lang, account["provider"], truncated=truncated,
            ),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("msg:more:"))
    async def on_msg_more(call: CallbackQuery) -> None:
        msg, account = await _load_owned_message(call)
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        if msg is None or account is None:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        text, _image, _truncated = build_notification(msg)
        await _edit_text_or_caption(
            call.message,
            text,
            notification_keyboard(msg["id"], lang, account["provider"], expanded=True),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("msg:less:"))
    async def on_msg_less(call: CallbackQuery) -> None:
        msg, account = await _load_owned_message(call)
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        if msg is None or account is None:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        text, _image, truncated = build_notification(msg)
        await _edit_text_or_caption(
            call.message,
            text,
            notification_keyboard(
                msg["id"], lang, account["provider"], truncated=truncated,
            ),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("msg:read:"))
    async def on_msg_read(call: CallbackQuery) -> None:
        msg, account = await _load_owned_message(call)
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        if msg is None or account is None:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        await db.mark_read(msg["id"])
        spawn_mark_read(db, account["id"], msg["provider_message_id"])
        await call.answer(i18n.t(lang, "marked_read"))

    @router.callback_query(F.data.startswith("msg:delete:"))
    async def on_msg_delete(call: CallbackQuery) -> None:
        msg, account = await _load_owned_message(call)
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        if msg is None or account is None:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        await db.delete_message(msg["id"])
        spawn_delete_provider(db, account["id"], msg["provider_message_id"])
        try:
            await call.message.delete()
        except Exception:  # noqa: BLE001 - best-effort chat cleanup
            logger.debug("Could not delete notification message %s", msg["id"])
        await call.answer(i18n.t(lang, "message_deleted"))

    @router.callback_query(F.data.startswith("msg:hide:"))
    async def on_msg_hide(call: CallbackQuery) -> None:
        msg, account = await _load_owned_message(call)
        user = await db.get_user(call.from_user.id)
        lang = (user or {}).get("language", "en")
        if msg is None or account is None:
            await call.answer(i18n.t(lang, "error_generic"), show_alert=True)
            return
        sender = (msg.get("sender_email") or "").strip()
        if sender:
            await db.add_muted_sender(call.from_user.id, sender)
            await db.delete_messages_from_sender(call.from_user.id, sender)
        try:
            await call.message.delete()
        except Exception:  # noqa: BLE001
            logger.debug("Could not delete notification message %s", msg["id"])
        await call.answer(i18n.t(lang, "sender_hidden", email=sender.upper() or "?"))


# ---------------------------------------------------------------------------
# Notification sender (used by the sync engine)
# ---------------------------------------------------------------------------
async def send_new_mail_notification(
    bot: Bot,
    db: Database,
    telegram_id: int,
    lang: str,
    message: dict,
    provider: str = "gmail",
) -> None:
    """Send a Telegram notification for a newly synced message.

    Text is rich: the email's own line structure and inline hyperlinks are
    preserved (parse_mode=HTML). When the email has an inline image the
    photo is sent alongside, and any text about the image is dropped.
    """
    text, image, _truncated = build_notification(message)
    keyboard = notification_keyboard(
        message["id"], lang, provider,
        truncated=_truncated, sender_email=message.get("sender_email"),
    )
    try:
        if image:
            try:
                await bot.send_photo(
                    telegram_id,
                    photo=image,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except Exception:  # noqa: BLE001 - image URL may be private/expired
                logger.info("Inline image send failed for %s, falling back", message["id"])
                await bot.send_message(
                    telegram_id,
                    text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
        else:
            await bot.send_message(
                telegram_id,
                text,
                parse_mode="HTML",
                reply_markup=keyboard,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        await db.mark_notified(message["id"])
    except Exception:  # noqa: BLE001 - notify failure must not break sync
        logger.exception("Failed to send notification for message %s", message["id"])
