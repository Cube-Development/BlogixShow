from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from aiogram.types import Message

from advertiser_blogger.presentation.bot.message_batch.models import MessageBatch, RegisterResult
from configuration.common import MessageBatchCollectorConfig

FlushCallback = Callable[[MessageBatch], Awaitable[bool]]


@dataclass
class _ChatBuffer:
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    message_ids: set[int] = field(default_factory=set)


class MessageBatchCollector:
    def __init__(
            self,
            config: MessageBatchCollectorConfig,
            on_flush: FlushCallback,
    ) -> None:
        self._config = config
        self._on_flush = on_flush
        self._buffers: dict[int, _ChatBuffer] = {}
        self._debounce_timers: dict[int, asyncio.Task[None]] = {}
        self._age_timers: dict[int, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def register(self, message: Message) -> RegisterResult:
        async with self._lock:
            chat_id = message.chat.id
            is_first = chat_id not in self._buffers
            buffer = self._buffers.get(chat_id)
            if buffer is None:
                buffer = _ChatBuffer()
                self._buffers[chat_id] = buffer
                self._schedule_age_flush(chat_id)

            if message.message_id in buffer.message_ids:
                return RegisterResult.PENDING

            buffer.messages.append(message)
            buffer.message_ids.add(message.message_id)

            if len(buffer.messages) >= self._config.max_items:
                self._cancel_debounce(chat_id)
                self._cancel_age(chat_id)
                asyncio.create_task(self._flush(chat_id))
                return RegisterResult.FIRST if is_first else RegisterResult.FLUSH_SCHEDULED

            self._schedule_debounce(chat_id)
            return RegisterResult.FIRST if is_first else RegisterResult.PENDING

    def has_open_buffer(self, chat_id: int) -> bool:
        return chat_id in self._buffers

    def _schedule_debounce(self, chat_id: int) -> None:
        self._cancel_debounce(chat_id)

        async def _debounced() -> None:
            try:
                await asyncio.sleep(self._config.debounce_ms / 1000)
                await self._flush(chat_id)
            except asyncio.CancelledError:
                raise

        self._debounce_timers[chat_id] = asyncio.create_task(_debounced())

    def _schedule_age_flush(self, chat_id: int) -> None:
        self._cancel_age(chat_id)

        async def _age_flush() -> None:
            try:
                await asyncio.sleep(self._config.max_batch_age_ms / 1000)
                await self._flush(chat_id)
            except asyncio.CancelledError:
                raise

        self._age_timers[chat_id] = asyncio.create_task(_age_flush())

    def _cancel_debounce(self, chat_id: int) -> None:
        task = self._debounce_timers.pop(chat_id, None)
        if task is None or task.done():
            return
        if task is asyncio.current_task():
            return
        task.cancel()

    def _cancel_age(self, chat_id: int) -> None:
        task = self._age_timers.pop(chat_id, None)
        if task is None or task.done():
            return
        if task is asyncio.current_task():
            return
        task.cancel()

    async def _flush(self, chat_id: int) -> None:
        self._cancel_debounce(chat_id)
        self._cancel_age(chat_id)
        buffer = self._buffers.pop(chat_id, None)
        if buffer is None or not buffer.messages:
            return

        sorted_messages = sorted(buffer.messages, key=lambda item: item.message_id)
        batch = MessageBatch(
            chat_id=chat_id,
            messages=sorted_messages,
            created_at=buffer.created_at,
        )
        await self._on_flush(batch)
