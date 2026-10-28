from structlog import get_logger
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from album_collector.collector import AlbumCollector
from album_collector.models import RegisterResult

logger = get_logger(__name__)


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

        update = data.get("event_update")
        update_id = update.update_id if update is not None else 0
        result = await self._collector.register_part(message=event, update_id=update_id)
        if result in {RegisterResult.PENDING, RegisterResult.FLUSH_SCHEDULED, RegisterResult.DUPLICATE}:
            return None
        if result is RegisterResult.IGNORED:
            logger.warning("album part ignored", chat_id=event.chat.id, media_group_id=event.media_group_id, message_id=event.message_id)
            return None
        return await handler(event, data)
