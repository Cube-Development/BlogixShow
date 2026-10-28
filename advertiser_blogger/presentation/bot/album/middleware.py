from structlog import get_logger
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from advertiser_blogger.domain.read.constants import Language
from advertiser_blogger.presentation.bot.album.collector import AlbumCollector
from advertiser_blogger.presentation.bot.album.models import RegisterResult
from advertiser_blogger.presentation.bot.common.project_create_draft import (
    maybe_send_processing_notice,
)
from advertiser_blogger.presentation.bot.common.project_create_texts import t
from advertiser_blogger.presentation.bot.filters.project_create import is_project_create_collecting_state

logger = get_logger(__name__)


def _language_from_data(data: dict[str, Any]) -> Language:
    user = data.get("user")
    language = getattr(user, "language", None) if user is not None else None
    if isinstance(language, Language):
        return language
    return Language.ru


class AlbumCollectorMiddleware(BaseMiddleware):
    def __init__(self, collector: AlbumCollector) -> None:
        self._collector = collector

    async def __call__(
            self,
            handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        if event.media_group_id is None:
            return await handler(event, data)

        state: FSMContext | None = data.get("state")
        update = data.get("event_update")
        update_id = update.update_id if update is not None else 0
        result = await self._collector.register_part(message=event, update_id=update_id)
        if (
            result in {RegisterResult.PENDING, RegisterResult.FLUSH_SCHEDULED}
            and state is not None
            and is_project_create_collecting_state(await state.get_state())
        ):
            await maybe_send_processing_notice(
                event,
                state,
                text=t(_language_from_data(data), "processing"),
            )
        if result in {RegisterResult.PENDING, RegisterResult.FLUSH_SCHEDULED, RegisterResult.DUPLICATE}:
            return None
        if result is RegisterResult.IGNORED:
            logger.warning("album part ignored", chat_id=event.chat.id, media_group_id=event.media_group_id, message_id=event.message_id)
            return None
        return await handler(event, data)
