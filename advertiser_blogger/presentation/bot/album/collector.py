import asyncio
from structlog import get_logger
from collections.abc import Awaitable, Callable
from datetime import datetime

from aiogram.types import Message

from advertiser_blogger.presentation.bot.album.models import AggregatedAlbum, AlbumPart, RegisterResult
from advertiser_blogger.presentation.bot.album.redis_store import AlbumBufferStore
from advertiser_blogger.presentation.bot.common.forward_message import get_forward_part_metadata
from configuration.common import AlbumCollectorConfig

logger = get_logger(__name__)

FlushCallback = Callable[[AggregatedAlbum, Message], Awaitable[bool]]


def message_to_album_part(message: Message, update_id: int) -> AlbumPart | None:
    caption = message.caption
    date = message.date or datetime.utcnow()
    (
        is_forward,
        forward_chat_id,
        forward_chat_username,
        forward_message_id,
        forward_date,
    ) = get_forward_part_metadata(message)
    forward_fields = {
        "is_forward": is_forward,
        "forward_chat_id": forward_chat_id,
        "forward_chat_username": forward_chat_username,
        "forward_message_id": forward_message_id,
        "forward_date": forward_date,
    }
    if message.photo:
        photo = message.photo[-1]
        return AlbumPart(
            update_id=update_id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            file_id=photo.file_id,
            file_unique_id=photo.file_unique_id,
            media_type="photo",
            caption=caption,
            date=date,
            **forward_fields,
        )
    if message.video:
        return AlbumPart(
            update_id=update_id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            file_id=message.video.file_id,
            file_unique_id=message.video.file_unique_id,
            media_type="video",
            caption=caption,
            date=date,
            **forward_fields,
        )
    if message.document:
        return AlbumPart(
            update_id=update_id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            file_id=message.document.file_id,
            file_unique_id=message.document.file_unique_id,
            media_type="document",
            caption=caption,
            date=date,
            **forward_fields,
        )
    return None


class AlbumCollector:
    def __init__(
            self,
            store: AlbumBufferStore,
            config: AlbumCollectorConfig,
            on_flush: FlushCallback,
    ) -> None:
        self._store = store
        self._config = config
        self._on_flush = on_flush
        self._timers: dict[tuple[int, str], asyncio.Task[None]] = {}
        self._last_messages: dict[tuple[int, str], Message] = {}

    async def register_part(self, message: Message, update_id: int) -> RegisterResult:
        media_group_id = message.media_group_id
        if media_group_id is None:
            return RegisterResult.IGNORED

        chat_id = message.chat.id
        if message.from_user is None:
            return RegisterResult.IGNORED

        if await self._store.is_processed(chat_id=chat_id, media_group_id=media_group_id):
            logger.warning("album part ignored: already processed", chat_id=chat_id, media_group_id=media_group_id, message_id=message.message_id)
            return RegisterResult.IGNORED

        part = message_to_album_part(message=message, update_id=update_id)
        if part is None:
            return RegisterResult.IGNORED

        status, flush_immediately = await self._store.append(
            part=part,
            media_group_id=media_group_id,
            user_id=message.from_user.id,
        )
        key = (chat_id, media_group_id)
        self._last_messages[key] = message

        if status == "duplicate":
            return RegisterResult.DUPLICATE

        if flush_immediately:
            self._cancel_timer(key=key)
            asyncio.create_task(self._flush(chat_id=chat_id, media_group_id=media_group_id))
            return RegisterResult.FLUSH_SCHEDULED

        self._schedule_flush(chat_id=chat_id, media_group_id=media_group_id)
        return RegisterResult.PENDING

    def _schedule_flush(self, chat_id: int, media_group_id: str) -> None:
        key = (chat_id, media_group_id)
        self._cancel_timer(key=key)

        async def _debounced_flush() -> None:
            try:
                await asyncio.sleep(self._config.debounce_ms / 1000)
                await self._flush(chat_id=chat_id, media_group_id=media_group_id)
            except asyncio.CancelledError:
                raise

        self._timers[key] = asyncio.create_task(_debounced_flush())

    def _cancel_timer(self, key: tuple[int, str]) -> None:
        task = self._timers.pop(key, None)
        if task is None or task.done():
            return
        # Не отменяем текущий task: _flush вызывается из debounce-timer,
        # иначе CancelledError прервёт flush на первом await.
        if task is asyncio.current_task():
            return
        task.cancel()

    async def _flush(self, chat_id: int, media_group_id: str) -> None:
        key = (chat_id, media_group_id)
        self._cancel_timer(key=key)
        last_message = self._last_messages.pop(key, None)

        lock_uuid = await self._store.acquire_flush_lock(chat_id=chat_id, media_group_id=media_group_id)
        if lock_uuid is None:
            return

        try:
            aggregated = await self._store.get(chat_id=chat_id, media_group_id=media_group_id)
            if aggregated is None:
                logger.warning("album buffer expired or missing", chat_id=chat_id, media_group_id=media_group_id)
                return

            if last_message is None:
                logger.warning("album flush: last message missing", chat_id=chat_id, media_group_id=media_group_id)
                return

            success = await self._on_flush(aggregated, last_message)
            if success:
                await self._store.mark_processed(chat_id=chat_id, media_group_id=media_group_id)
                await self._store.delete(chat_id=chat_id, media_group_id=media_group_id)
            else:
                logger.warning("album flush not committed", chat_id=chat_id, media_group_id=media_group_id)
        finally:
            await self._store.release_flush_lock(
                chat_id=chat_id, media_group_id=media_group_id, lock_uuid=lock_uuid,
            )
