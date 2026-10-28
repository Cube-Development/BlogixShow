from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import Message


class IsNotTelegramBotCommand(Filter):
    """Let CommandStart and other bot commands fall through to UserRouter."""

    async def __call__(self, message: Message) -> bool:
        if message.entities:
            if any(entity.type == "bot_command" for entity in message.entities):
                return False
        body = message.text or message.caption
        if body and body.startswith("/"):
            return False
        return True
