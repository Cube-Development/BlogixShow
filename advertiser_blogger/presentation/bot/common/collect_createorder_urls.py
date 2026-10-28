from __future__ import annotations

from html import escape
from urllib.parse import urlparse
from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup


def build_collect_createorder_return_url(frontend_domain: str, project_id: UUID) -> str:
    base = frontend_domain.rstrip("/")
    return f"{base}/createorder?project_id={project_id}&reset_datetime=true#post"


def is_telegram_inline_url_allowed(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return False
    return bool(host)


def build_collect_success_message_html(success_text: str, project_url: str) -> str:
    safe_url = escape(project_url, quote=True)
    return f"{escape(success_text)}\n<a href=\"{safe_url}\">Продолжить на сайте</a>"


def _is_message_not_modified(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in str(exc).lower()


async def edit_collect_callback_text(
        *,
        bot: Bot,
        callback: CallbackQuery,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        parse_mode: str | None = None,
) -> None:
    message = callback.message
    if message is None or getattr(message, "chat", None) is None:
        return
    chat_id = message.chat.id
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        return
    except TelegramBadRequest as exc:
        if _is_message_not_modified(exc):
            return
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )


async def edit_collect_success_notification(
        *,
        bot: Bot,
        callback: CallbackQuery,
        success_text: str,
        project_url: str,
        inline_success_keyboard: InlineKeyboardMarkup,
) -> None:
    if is_telegram_inline_url_allowed(project_url):
        await edit_collect_callback_text(
            bot=bot,
            callback=callback,
            text=success_text,
            reply_markup=inline_success_keyboard,
        )
        return
    await edit_collect_callback_text(
        bot=bot,
        callback=callback,
        text=build_collect_success_message_html(success_text, project_url),
        parse_mode="HTML",
    )
