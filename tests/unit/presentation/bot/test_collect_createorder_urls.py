from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from advertiser_blogger.presentation.bot.common.collect_createorder_urls import (
    build_collect_createorder_return_url,
    build_collect_success_message_html,
    edit_collect_callback_text,
    edit_collect_success_notification,
    is_telegram_inline_url_allowed,
)


def test_build_collect_createorder_return_url() -> None:
    project_id = uuid4()
    url = build_collect_createorder_return_url("https://app.example.com/", project_id)
    assert url == (
        f"https://app.example.com/createorder?project_id={project_id}&reset_datetime=true#post"
    )


def test_build_collect_success_message_html_contains_link() -> None:
    html = build_collect_success_message_html("OK", "http://localhost:5173/createorder?project_id=x#post")
    assert "<a href=" in html
    assert "Продолжить на сайте</a>" in html


def test_is_telegram_inline_url_rejects_localhost() -> None:
    assert is_telegram_inline_url_allowed("http://localhost:5173/createorder") is False
    assert is_telegram_inline_url_allowed("https://app.example.com/createorder") is True


def test_edit_collect_callback_text_edits_existing_message() -> None:
    async def _run():
        bot = MagicMock()
        bot.edit_message_text = AsyncMock()
        bot.send_message = AsyncMock()
        callback = MagicMock()
        callback.message.chat.id = 11
        callback.message.message_id = 22
        await edit_collect_callback_text(bot=bot, callback=callback, text="edited")
        bot.edit_message_text.assert_awaited_once()
        bot.send_message.assert_not_awaited()

    asyncio.run(_run())


def test_edit_collect_callback_text_falls_back_to_send() -> None:
    async def _run():
        bot = MagicMock()
        bot.edit_message_text = AsyncMock(side_effect=TelegramBadRequest(method=MagicMock(), message="can't edit"))
        bot.send_message = AsyncMock()
        callback = MagicMock()
        callback.message.chat.id = 11
        callback.message.message_id = 22
        await edit_collect_callback_text(bot=bot, callback=callback, text="fallback")
        bot.send_message.assert_awaited_once()

    asyncio.run(_run())


def test_edit_collect_success_uses_keyboard_for_public_https() -> None:
    async def _run():
        bot = MagicMock()
        bot.edit_message_text = AsyncMock()
        callback = MagicMock()
        callback.message.chat.id = 11
        callback.message.message_id = 22
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        await edit_collect_success_notification(
            bot=bot,
            callback=callback,
            success_text="OK",
            project_url="https://blogix.uz/createorder?project_id=x#post",
            inline_success_keyboard=keyboard,
        )
        kwargs = bot.edit_message_text.await_args.kwargs
        assert kwargs["text"] == "OK"
        assert kwargs["reply_markup"] is keyboard

    asyncio.run(_run())
