from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from aiogram.types import MessageEntity

from advertiser_blogger.presentation.bot.filters.collect_createorder_message import (
    IsNotTelegramBotCommand,
)
from advertiser_blogger.presentation.bot.handlers.user.collect_createorder import (
    CollectCreateorderRouter,
    collect_receive_post_message,
    collect_unlinked_message,
)


def _message(text: str, *, entities: list[MessageEntity] | None = None) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.caption = None
    msg.entities = entities
    return msg


def test_is_not_telegram_bot_command_rejects_start_with_payload() -> None:
    filt = IsNotTelegramBotCommand()
    msg = _message(
        "/start compact_payload",
        entities=[MessageEntity(type="bot_command", offset=0, length=6)],
    )

    async def _run():
        assert await filt(msg) is False

    asyncio.run(_run())


def test_is_not_telegram_bot_command_rejects_plain_start() -> None:
    filt = IsNotTelegramBotCommand()

    async def _run():
        assert await filt(_message("/start")) is False

    asyncio.run(_run())


def test_is_not_telegram_bot_command_rejects_other_commands() -> None:
    filt = IsNotTelegramBotCommand()
    msg = _message(
        "/topic",
        entities=[MessageEntity(type="bot_command", offset=0, length=6)],
    )

    async def _run():
        assert await filt(msg) is False

    asyncio.run(_run())


def test_is_not_telegram_bot_command_allows_normal_post_text() -> None:
    filt = IsNotTelegramBotCommand()

    async def _run():
        assert await filt(_message("готовый пост для рекламы")) is True

    asyncio.run(_run())


def test_collect_unlinked_handler_registers_command_exclusion() -> None:
    observer = CollectCreateorderRouter.observers.get("message")
    assert observer is not None
    registered = next(r for r in observer.handlers if r.callback is collect_unlinked_message)
    assert any(
        isinstance(getattr(f, "callback", None), IsNotTelegramBotCommand) for f in registered.filters
    )


def test_collect_receive_post_handler_registers_command_exclusion() -> None:
    observer = CollectCreateorderRouter.observers.get("message")
    assert observer is not None
    registered = next(r for r in observer.handlers if r.callback is collect_receive_post_message)
    assert any(
        isinstance(getattr(f, "callback", None), IsNotTelegramBotCommand) for f in registered.filters
    )
