import json
from dataclasses import asdict
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from redis.asyncio import Redis

from album_collector.models import AggregatedAlbum, AlbumPart
from album_collector.config import AlbumCollectorConfig


APPEND_SCRIPT = """
local existing = redis.call('GET', KEYS[1])
local part = cjson.decode(ARGV[1])
local buffer
if existing then
  buffer = cjson.decode(existing)
else
  buffer = cjson.decode(ARGV[4])
end
for _, item in ipairs(buffer.parts) do
  if tonumber(item.message_id) == tonumber(part.message_id) then
    return cjson.encode({status='duplicate', parts_count=#buffer.parts, flush_immediately=false})
  end
end
table.insert(buffer.parts, part)
buffer.updated_at = ARGV[5]
local max_items = tonumber(ARGV[3])
local flush_immediately = #buffer.parts >= max_items
redis.call('SET', KEYS[1], cjson.encode(buffer), 'EX', tonumber(ARGV[2]))
return cjson.encode({status='ok', parts_count=#buffer.parts, flush_immediately=flush_immediately})
"""

RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


def buffer_key(chat_id: int, media_group_id: str) -> str:
    return f"telegram:album:{chat_id}:{media_group_id}"


def flush_lock_key(chat_id: int, media_group_id: str) -> str:
    return f"telegram:album:flush_lock:{chat_id}:{media_group_id}"


def processed_key(chat_id: int, media_group_id: str) -> str:
    return f"telegram:album:processed:{chat_id}:{media_group_id}"


def _part_to_dict(part: AlbumPart) -> dict:
    data = asdict(part)
    data["date"] = part.date.isoformat()
    if part.forward_date is not None:
        data["forward_date"] = part.forward_date.isoformat()
    else:
        data["forward_date"] = None
    return data


def _part_from_dict(data: dict) -> AlbumPart:
    forward_date_raw = data.get("forward_date")
    return AlbumPart(
        update_id=data["update_id"],
        chat_id=data["chat_id"],
        message_id=data["message_id"],
        file_id=data["file_id"],
        file_unique_id=data.get("file_unique_id"),
        media_type=data["media_type"],
        caption=data.get("caption"),
        date=datetime.fromisoformat(data["date"]),
        is_forward=data.get("is_forward", False),
        forward_chat_id=data.get("forward_chat_id"),
        forward_chat_username=data.get("forward_chat_username"),
        forward_message_id=data.get("forward_message_id"),
        forward_date=datetime.fromisoformat(forward_date_raw) if forward_date_raw else None,
    )


def _buffer_from_dict(data: dict) -> AggregatedAlbum:
    return AggregatedAlbum(
        media_group_id=data["media_group_id"],
        chat_id=data["chat_id"],
        user_id=data["user_id"],
        parts=[_part_from_dict(item) for item in data.get("parts", [])],
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
    )


class AlbumBufferStore(Protocol):
    async def is_processed(self, chat_id: int, media_group_id: str) -> bool: ...

    async def append(
            self,
            part: AlbumPart,
            media_group_id: str,
            user_id: int,
    ) -> tuple[str, bool]: ...

    async def get(self, chat_id: int, media_group_id: str) -> AggregatedAlbum | None: ...

    async def delete(self, chat_id: int, media_group_id: str) -> None: ...

    async def acquire_flush_lock(self, chat_id: int, media_group_id: str) -> str | None: ...

    async def release_flush_lock(self, chat_id: int, media_group_id: str, lock_uuid: str) -> None: ...

    async def mark_processed(self, chat_id: int, media_group_id: str) -> None: ...


class RedisAlbumBufferStore:
    def __init__(self, redis: Redis, config: AlbumCollectorConfig) -> None:
        self._redis = redis
        self._config = config
        self._append_script = self._redis.register_script(APPEND_SCRIPT)
        self._release_lock_script = self._redis.register_script(RELEASE_LOCK_SCRIPT)

    async def is_processed(self, chat_id: int, media_group_id: str) -> bool:
        return bool(await self._redis.exists(processed_key(chat_id=chat_id, media_group_id=media_group_id)))

    async def append(
            self,
            part: AlbumPart,
            media_group_id: str,
            user_id: int,
    ) -> tuple[str, bool]:
        now = datetime.utcnow().isoformat()
        skeleton = {
            "media_group_id": media_group_id,
            "chat_id": part.chat_id,
            "user_id": user_id,
            "parts": [],
            "created_at": now,
            "updated_at": now,
        }
        result_raw = await self._append_script(
            keys=[buffer_key(chat_id=part.chat_id, media_group_id=media_group_id)],
            args=[
                json.dumps(_part_to_dict(part)),
                str(self._config.buffer_ttl_sec),
                str(self._config.max_items),
                json.dumps(skeleton),
                now,
            ],
        )
        result = json.loads(result_raw)
        return result["status"], bool(result.get("flush_immediately"))

    async def get(self, chat_id: int, media_group_id: str) -> AggregatedAlbum | None:
        key = buffer_key(chat_id=chat_id, media_group_id=media_group_id)
        payload = await self._redis.get(key)
        if payload is None:
            return None
        aggregated = _buffer_from_dict(json.loads(payload))
        return aggregated

    async def delete(self, chat_id: int, media_group_id: str) -> None:
        await self._redis.delete(buffer_key(chat_id=chat_id, media_group_id=media_group_id))

    async def acquire_flush_lock(self, chat_id: int, media_group_id: str) -> str | None:
        lock_uuid = str(uuid4())
        acquired = await self._redis.set(
            flush_lock_key(chat_id=chat_id, media_group_id=media_group_id),
            lock_uuid,
            nx=True,
            ex=self._config.flush_lock_ttl_sec,
        )
        if not acquired:
            return None
        return lock_uuid

    async def release_flush_lock(self, chat_id: int, media_group_id: str, lock_uuid: str) -> None:
        await self._release_lock_script(
            keys=[flush_lock_key(chat_id=chat_id, media_group_id=media_group_id)],
            args=[lock_uuid],
        )

    async def mark_processed(self, chat_id: int, media_group_id: str) -> None:
        await self._redis.set(
            processed_key(chat_id=chat_id, media_group_id=media_group_id),
            "1",
            ex=self._config.processed_ttl_sec,
        )
