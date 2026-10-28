from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from advertiser_blogger.domain.read.constants import Language
from advertiser_blogger.presentation.bot.common.project_create_draft import (
    maybe_send_processing_notice,
)
from advertiser_blogger.presentation.bot.common.project_create_texts import t
from advertiser_blogger.presentation.bot.filters.project_create import (
    MENU_NAVIGATION_TEXTS,
    is_project_create_collecting_state,
)
from advertiser_blogger.presentation.bot.message_batch.collector import MessageBatchCollector
from advertiser_blogger.presentation.bot.message_batch.models import RegisterResult


def _should_buffer_message(message: Message, current_state: str | None) -> bool:
    if message.media_group_id is not None:
        return False
    if not is_project_create_collecting_state(current_state):
        return False
    # Channel-card edit flows must reach dedicated handlers, not the batch FSM.
    state_name = str(current_state or "")
    if any(
        name in state_name
        for name in (
            "awaiting_replace",
            "awaiting_replace_post",
            "awaiting_edit_schedule",
            "awaiting_edit_comment",
            "channel_menu",
            "confirming",
        )
    ):
        return False
    text = (message.text or message.caption or "").strip()
    if text.startswith("/"):
        return False
    if text in MENU_NAVIGATION_TEXTS:
        return False
    return True


def _language_from_data(data: dict[str, Any]) -> Language:
    user = data.get("user")
    language = getattr(user, "language", None) if user is not None else None
    if isinstance(language, Language):
        return language
    return Language.ru


class MessageBatchCollectorMiddleware(BaseMiddleware):
    def __init__(self, collector: MessageBatchCollector) -> None:
        self._collector = collector

    async def __call__(
            self,
            handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        state: FSMContext | None = data.get("state")
        current_state = await state.get_state() if state is not None else None
        if not _should_buffer_message(event, current_state):
            return await handler(event, data)

        result = await self._collector.register(event)
        if result is RegisterResult.FIRST and state is not None:
            await maybe_send_processing_notice(
                event,
                state,
                text=t(_language_from_data(data), "processing"),
            )
        if result in {
            RegisterResult.FIRST,
            RegisterResult.PENDING,
            RegisterResult.FLUSH_SCHEDULED,
        }:
            return None
        return await handler(event, data)
