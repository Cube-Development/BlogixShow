import asyncio
import json
from dataclasses import asdict
from datetime import datetime

from advertiser_blogger.presentation.bot.album.models import AggregatedAlbum, AlbumPart
from advertiser_blogger.presentation.bot.album.redis_store import AlbumBufferStore
from configuration.common import AlbumCollectorConfig


class InMemoryAlbumBufferStore:
    """Test-only buffer store; not used in production DI."""

    def __init__(self, config: AlbumCollectorConfig) -> None:
        self._config = config
        self._buffers: dict[str, dict] = {}
        self._locks: dict[str, str] = {}
        self._processed: set[str] = set()
        self._lock = asyncio.Lock()

    def _key(self, chat_id: int, media_group_id: str) -> str:
        return f"{chat_id}:{media_group_id}"

    async def is_processed(self, chat_id: int, media_group_id: str) -> bool:
        return self._key(chat_id, media_group_id) in self._processed

    async def append(
            self,
            part: AlbumPart,
            media_group_id: str,
            user_id: int,
    ) -> tuple[str, bool]:
        async with self._lock:
            key = self._key(part.chat_id, media_group_id)
            now = datetime.utcnow().isoformat()
            buffer = self._buffers.get(key)
            if buffer is None:
                buffer = {
                    "media_group_id": media_group_id,
                    "chat_id": part.chat_id,
                    "user_id": user_id,
                    "parts": [],
                    "created_at": now,
                    "updated_at": now,
                }
            for item in buffer["parts"]:
                if item["message_id"] == part.message_id:
                    return "duplicate", False
            part_dict = asdict(part)
            part_dict["date"] = part.date.isoformat()
            if part.forward_date is not None:
                part_dict["forward_date"] = part.forward_date.isoformat()
            buffer["parts"].append(part_dict)
            buffer["updated_at"] = now
            self._buffers[key] = buffer
            flush_immediately = len(buffer["parts"]) >= self._config.max_items
            return "ok", flush_immediately

    async def get(self, chat_id: int, media_group_id: str) -> AggregatedAlbum | None:
        key = self._key(chat_id, media_group_id)
        buffer = self._buffers.get(key)
        if buffer is None:
            return None
        return AggregatedAlbum(
            media_group_id=buffer["media_group_id"],
            chat_id=buffer["chat_id"],
            user_id=buffer["user_id"],
            parts=[
                AlbumPart(
                    update_id=item["update_id"],
                    chat_id=item["chat_id"],
                    message_id=item["message_id"],
                    file_id=item["file_id"],
                    file_unique_id=item.get("file_unique_id"),
                    media_type=item["media_type"],
                    caption=item.get("caption"),
                    date=datetime.fromisoformat(item["date"]),
                    is_forward=item.get("is_forward", False),
                    forward_chat_id=item.get("forward_chat_id"),
                    forward_chat_username=item.get("forward_chat_username"),
                    forward_message_id=item.get("forward_message_id"),
                    forward_date=(
                        datetime.fromisoformat(item["forward_date"])
                        if item.get("forward_date")
                        else None
                    ),
                )
                for item in buffer["parts"]
            ],
            created_at=datetime.fromisoformat(buffer["created_at"]),
            updated_at=datetime.fromisoformat(buffer["updated_at"]),
        )

    async def delete(self, chat_id: int, media_group_id: str) -> None:
        self._buffers.pop(self._key(chat_id, media_group_id), None)

    async def acquire_flush_lock(self, chat_id: int, media_group_id: str) -> str | None:
        key = self._key(chat_id, media_group_id)
        if key in self._locks:
            return None
        lock_uuid = "test-lock"
        self._locks[key] = lock_uuid
        return lock_uuid

    async def release_flush_lock(self, chat_id: int, media_group_id: str, lock_uuid: str) -> None:
        key = self._key(chat_id, media_group_id)
        if self._locks.get(key) == lock_uuid:
            self._locks.pop(key, None)

    async def mark_processed(self, chat_id: int, media_group_id: str) -> None:
        self._processed.add(self._key(chat_id, media_group_id))
