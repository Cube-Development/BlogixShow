import asyncio
from datetime import datetime, timezone

import fakeredis.aioredis

from advertiser_blogger.presentation.bot.album.models import AlbumPart
from advertiser_blogger.presentation.bot.album.redis_store import (
    RedisAlbumBufferStore,
    flush_lock_key,
)
from advertiser_blogger.presentation.bot.common.extract_post_submission import extract_post_submission_from_album
from advertiser_blogger.presentation.bot.common.forward_message import telegram_chat_id_to_channel_ident
from configuration.common import AlbumCollectorConfig


def _make_part(message_id: int, chat_id: int = 123) -> AlbumPart:
    return AlbumPart(
        update_id=message_id,
        chat_id=chat_id,
        message_id=message_id,
        file_id=f"file-{message_id}",
        file_unique_id=f"unique-{message_id}",
        media_type="photo",
        caption=None,
        date=datetime.now(timezone.utc),
    )


def test_concurrent_append() -> None:
    async def _run() -> None:
        config = AlbumCollectorConfig(
            enabled=True,
            debounce_ms=1000,
            buffer_ttl_sec=30,
            max_items=10,
            flush_lock_ttl_sec=30,
            processed_ttl_sec=86400,
        )
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAlbumBufferStore(redis=redis, config=config)
        part1 = _make_part(message_id=100)
        part2 = _make_part(message_id=101)
        await asyncio.gather(
            store.append(part=part1, media_group_id="abc", user_id=456),
            store.append(part=part2, media_group_id="abc", user_id=456),
        )
        aggregated = await store.get(chat_id=123, media_group_id="abc")
        assert aggregated is not None
        assert len(aggregated.parts) == 2

    asyncio.run(_run())


def test_flush_lock_only_one_winner() -> None:
    async def _run() -> None:
        config = AlbumCollectorConfig(
            enabled=True,
            debounce_ms=1000,
            buffer_ttl_sec=30,
            max_items=10,
            flush_lock_ttl_sec=30,
            processed_ttl_sec=86400,
        )
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAlbumBufferStore(redis=redis, config=config)
        lock1 = await store.acquire_flush_lock(chat_id=123, media_group_id="abc")
        lock2 = await store.acquire_flush_lock(chat_id=123, media_group_id="abc")
        assert lock1 is not None
        assert lock2 is None

    asyncio.run(_run())


def test_release_own_lock() -> None:
    async def _run() -> None:
        config = AlbumCollectorConfig(
            enabled=True,
            debounce_ms=1000,
            buffer_ttl_sec=30,
            max_items=10,
            flush_lock_ttl_sec=30,
            processed_ttl_sec=86400,
        )
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAlbumBufferStore(redis=redis, config=config)
        lock_uuid = await store.acquire_flush_lock(chat_id=123, media_group_id="abc")
        assert lock_uuid is not None
        await store.release_flush_lock(
            chat_id=123, media_group_id="abc", lock_uuid="wrong-uuid",
        )
        assert await store._redis.exists(flush_lock_key(123, "abc"))
        await store.release_flush_lock(
            chat_id=123, media_group_id="abc", lock_uuid=lock_uuid,
        )
        assert not await store._redis.exists(flush_lock_key(123, "abc"))

    asyncio.run(_run())


def test_buffer_ttl_expires() -> None:
    async def _run() -> None:
        config = AlbumCollectorConfig(
            enabled=True,
            debounce_ms=1000,
            buffer_ttl_sec=1,
            max_items=10,
            flush_lock_ttl_sec=30,
            processed_ttl_sec=86400,
        )
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAlbumBufferStore(redis=redis, config=config)
        part = _make_part(message_id=100)
        await store.append(part=part, media_group_id="abc", user_id=456)
        await asyncio.sleep(1.1)
        assert await store.get(chat_id=123, media_group_id="abc") is None

    asyncio.run(_run())


def test_processed_key() -> None:
    async def _run() -> None:
        config = AlbumCollectorConfig(
            enabled=True,
            debounce_ms=1000,
            buffer_ttl_sec=30,
            max_items=10,
            flush_lock_ttl_sec=30,
            processed_ttl_sec=86400,
        )
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAlbumBufferStore(redis=redis, config=config)
        assert not await store.is_processed(chat_id=123, media_group_id="abc")
        await store.mark_processed(chat_id=123, media_group_id="abc")
        assert await store.is_processed(chat_id=123, media_group_id="abc")

    asyncio.run(_run())


def test_forward_metadata_redis_round_trip() -> None:
    async def _run() -> None:
        config = AlbumCollectorConfig(
            enabled=True,
            debounce_ms=1000,
            buffer_ttl_sec=30,
            max_items=10,
            flush_lock_ttl_sec=30,
            processed_ttl_sec=86400,
        )
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAlbumBufferStore(redis=redis, config=config)
        forward_chat_id = -1001234567890
        forward_part = AlbumPart(
            update_id=1,
            chat_id=123,
            message_id=100,
            file_id="file-100",
            file_unique_id="unique-100",
            media_type="photo",
            caption=None,
            date=datetime.now(timezone.utc),
            is_forward=True,
            forward_chat_id=forward_chat_id,
            forward_chat_username="testchannel",
            forward_message_id=42,
            forward_date=datetime.now(timezone.utc),
        )
        caption_part = AlbumPart(
            update_id=2,
            chat_id=123,
            message_id=101,
            file_id="file-101",
            file_unique_id="unique-101",
            media_type="photo",
            caption="album caption",
            date=datetime.now(timezone.utc),
        )
        await store.append(part=forward_part, media_group_id="abc", user_id=456)
        await store.append(part=caption_part, media_group_id="abc", user_id=456)

        aggregated = await store.get(chat_id=123, media_group_id="abc")
        assert aggregated is not None
        assert aggregated.forward_part is not None
        assert aggregated.forward_part.forward_chat_username == "testchannel"

        submission = extract_post_submission_from_album(aggregated=aggregated)
        assert submission.post_url == "https://t.me/testchannel/42"
        assert submission.channel_ident == telegram_chat_id_to_channel_ident(forward_chat_id)
        assert submission.channel_username == "testchannel"
        assert submission.text == "album caption"
        assert submission.is_album is True
        assert len(submission.media) == 2

    asyncio.run(_run())
