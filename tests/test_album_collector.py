import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram.enums import MessageOriginType
from aiogram.types import Chat, Message, MessageOriginChannel, PhotoSize, User

from album_collector.collector import AlbumCollector, message_to_album_part
from album_collector.memory_store import InMemoryAlbumBufferStore
from album_collector.models import RegisterResult
from album_collector.post_submission import (
    PostSubmissionInput,
    extract_post_submission_from_album,
    submission_from_json,
    submission_to_json,
)
from album_collector.models import AggregatedAlbum, AlbumPart
from album_collector.forward_message import telegram_chat_id_to_channel_ident
from album_collector.config import AlbumCollectorConfig


def _make_message(
        message_id: int,
        media_group_id: str,
        caption: str | None = None,
        user_id: int = 456,
        chat_id: int = 123,
) -> Message:
    photo = PhotoSize(
        file_id=f"file-{message_id}",
        file_unique_id=f"unique-{message_id}",
        width=100,
        height=100,
    )
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="Test"),
        media_group_id=media_group_id,
        photo=[photo],
        caption=caption,
    )


def _make_forward_message(
        message_id: int,
        media_group_id: str,
        *,
        forward_message_id: int = 42,
        forward_chat_id: int = -1001234567890,
        forward_username: str = "testchannel",
        caption: str | None = None,
        user_id: int = 456,
        chat_id: int = 123,
) -> Message:
    photo = PhotoSize(
        file_id=f"file-{message_id}",
        file_unique_id=f"unique-{message_id}",
        width=100,
        height=100,
    )
    forward_date = datetime.now(timezone.utc)
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="Test"),
        media_group_id=media_group_id,
        photo=[photo],
        caption=caption,
        forward_origin=MessageOriginChannel(
            type=MessageOriginType.CHANNEL,
            date=forward_date,
            chat=Chat(id=forward_chat_id, type="channel", username=forward_username),
            message_id=forward_message_id,
        ),
    )


@pytest.fixture
def album_config() -> AlbumCollectorConfig:
    return AlbumCollectorConfig(
        enabled=True,
        debounce_ms=50,
        buffer_ttl_sec=30,
        max_items=10,
        flush_lock_ttl_sec=5,
        processed_ttl_sec=86400,
    )


def test_collector_debounce_flushes_all_parts(album_config: AlbumCollectorConfig) -> None:
    async def _run() -> None:
        flushed: list[tuple[AggregatedAlbum, Message]] = []

        async def on_flush(aggregated: AggregatedAlbum, message: Message) -> bool:
            flushed.append((aggregated, message))
            return True

        store = InMemoryAlbumBufferStore(config=album_config)
        collector = AlbumCollector(store=store, config=album_config, on_flush=on_flush)

        message1 = _make_message(message_id=100, media_group_id="abc")
        message2 = _make_message(message_id=101, media_group_id="abc", caption="post text https://t.me/channel/1")

        assert await collector.register_part(message=message1, update_id=1) is RegisterResult.PENDING
        assert await collector.register_part(message=message2, update_id=2) is RegisterResult.PENDING

        await asyncio.sleep(0.08)
        await asyncio.sleep(0)

        assert len(flushed) == 1
        assert len(flushed[0][0].parts) == 2
        assert flushed[0][0].caption == "post text https://t.me/channel/1"

    asyncio.run(_run())


def test_forward_album_preserves_forward_context(album_config: AlbumCollectorConfig) -> None:
    async def _run() -> None:
        submissions: list[PostSubmissionInput] = []

        async def on_flush(aggregated: AggregatedAlbum, message: Message) -> bool:
            submissions.append(extract_post_submission_from_album(aggregated=aggregated))
            return True

        store = InMemoryAlbumBufferStore(config=album_config)
        collector = AlbumCollector(store=store, config=album_config, on_flush=on_flush)

        forward_chat_id = -1001234567890
        message1 = _make_forward_message(message_id=100, media_group_id="abc")
        message2 = _make_message(message_id=101, media_group_id="abc", caption="album caption")

        part1 = message_to_album_part(message=message1, update_id=1)
        part2 = message_to_album_part(message=message2, update_id=2)
        assert part1 is not None and part1.is_forward is True
        assert part2 is not None and part2.is_forward is False

        assert await collector.register_part(message=message1, update_id=1) is RegisterResult.PENDING
        assert await collector.register_part(message=message2, update_id=2) is RegisterResult.PENDING

        await asyncio.sleep(0.08)
        await asyncio.sleep(0)

        assert len(submissions) == 1
        submission = submissions[0]
        assert submission.is_album is True
        assert submission.post_url == "https://t.me/testchannel/42"
        assert submission.channel_ident == telegram_chat_id_to_channel_ident(forward_chat_id)
        assert submission.channel_username == "testchannel"
        assert submission.text == "album caption"
        assert len(submission.media) == 2

    asyncio.run(_run())


def test_caption_album_flow_unchanged(album_config: AlbumCollectorConfig) -> None:
    async def _run() -> None:
        submissions: list[PostSubmissionInput] = []

        async def on_flush(aggregated: AggregatedAlbum, message: Message) -> bool:
            submissions.append(
                extract_post_submission_from_album(aggregated=aggregated, source_message=message),
            )
            return True

        store = InMemoryAlbumBufferStore(config=album_config)
        collector = AlbumCollector(store=store, config=album_config, on_flush=on_flush)

        message1 = _make_message(message_id=100, media_group_id="abc")
        message2 = _make_message(
            message_id=101,
            media_group_id="abc",
            caption="post text https://t.me/channel/1",
        )

        assert await collector.register_part(message=message1, update_id=1) is RegisterResult.PENDING
        assert await collector.register_part(message=message2, update_id=2) is RegisterResult.PENDING

        await asyncio.sleep(0.08)
        await asyncio.sleep(0)

        assert len(submissions) == 1
        submission = submissions[0]
        assert submission.is_album is True
        assert submission.text == "post text https://t.me/channel/1"
        assert submission.post_url == "https://t.me/channel/1"
        assert submission.channel_username == "channel"
        assert len(submission.media) == 2

    asyncio.run(_run())


def test_collector_deduplicates_same_message_id(album_config: AlbumCollectorConfig) -> None:
    async def _run() -> None:
        flushed: list[AggregatedAlbum] = []

        async def on_flush(aggregated: AggregatedAlbum, message: Message) -> bool:
            flushed.append(aggregated)
            return True

        store = InMemoryAlbumBufferStore(config=album_config)
        collector = AlbumCollector(store=store, config=album_config, on_flush=on_flush)
        message = _make_message(message_id=100, media_group_id="abc", caption="text")

        assert await collector.register_part(message=message, update_id=1) is RegisterResult.PENDING
        assert await collector.register_part(message=message, update_id=2) is RegisterResult.DUPLICATE

        await asyncio.sleep(0.08)
        await asyncio.sleep(0)
        assert len(flushed) == 1
        assert len(flushed[0].parts) == 1

    asyncio.run(_run())


def test_collector_max_items_flushes_immediately(album_config: AlbumCollectorConfig) -> None:
    async def _run() -> None:
        config = AlbumCollectorConfig(
            enabled=True,
            debounce_ms=1000,
            buffer_ttl_sec=30,
            max_items=2,
            flush_lock_ttl_sec=5,
            processed_ttl_sec=86400,
        )
        flushed: list[AggregatedAlbum] = []

        async def on_flush(aggregated: AggregatedAlbum, message: Message) -> bool:
            flushed.append(aggregated)
            return True

        store = InMemoryAlbumBufferStore(config=config)
        collector = AlbumCollector(store=store, config=config, on_flush=on_flush)

        await collector.register_part(message=_make_message(100, "abc"), update_id=1)
        result = await collector.register_part(message=_make_message(101, "abc", caption="text"), update_id=2)
        assert result is RegisterResult.FLUSH_SCHEDULED

        await asyncio.sleep(0.05)
        await asyncio.sleep(0)
        assert len(flushed) == 1
        assert len(flushed[0].parts) == 2

    asyncio.run(_run())


def test_collector_ignores_processed_album(album_config: AlbumCollectorConfig) -> None:
    async def _run() -> None:
        store = InMemoryAlbumBufferStore(config=album_config)
        await store.mark_processed(chat_id=123, media_group_id="abc")

        collector = AlbumCollector(
            store=store,
            config=album_config,
            on_flush=AsyncMock(),
        )
        result = await collector.register_part(
            message=_make_message(100, "abc", caption="text"),
            update_id=1,
        )
        assert result is RegisterResult.IGNORED

    asyncio.run(_run())


def test_extract_post_submission_from_album_caption() -> None:
    aggregated = AggregatedAlbum(
        media_group_id="abc",
        chat_id=123,
        user_id=456,
        parts=[
            AlbumPart(
                update_id=1,
                chat_id=123,
                message_id=100,
                file_id="file-1",
                file_unique_id="unique-1",
                media_type="photo",
                caption="hello https://t.me/channel/10",
                date=datetime.now(timezone.utc),
            ),
        ],
    )
    submission = extract_post_submission_from_album(aggregated=aggregated)
    assert submission.is_album is True
    assert submission.media_group_id == "abc"
    assert submission.text == "hello https://t.me/channel/10"
    assert submission.post_url == "https://t.me/channel/10"
    assert len(submission.media) == 1


def test_submission_round_trip_with_album_fields() -> None:
    submission = PostSubmissionInput(
        channel_ident=None,
        channel_username="channel",
        post_url="https://t.me/channel/10",
        text="caption",
        media_group_id="abc",
        media=(),
        primary_message_id=100,
        is_album=True,
    )
    restored = submission_from_json(payload=submission_to_json(submission=submission))
    assert restored == submission


def test_message_to_album_part() -> None:
    message = _make_message(message_id=10, media_group_id="abc", caption="cap")
    part = message_to_album_part(message=message, update_id=5)
    assert part is not None
    assert part.update_id == 5
    assert part.file_unique_id == "unique-10"


def _setup_collector_for_flush(
        album_config: AlbumCollectorConfig,
        on_flush,
) -> tuple[AlbumCollector, InMemoryAlbumBufferStore]:
    store = InMemoryAlbumBufferStore(config=album_config)
    collector = AlbumCollector(store=store, config=album_config, on_flush=on_flush)
    return collector, store


def test_flush_commits_on_success(album_config: AlbumCollectorConfig) -> None:
    async def _run() -> None:
        async def on_flush(aggregated: AggregatedAlbum, message: Message) -> bool:
            return True

        collector, store = _setup_collector_for_flush(album_config, on_flush)
        message = _make_message(message_id=100, media_group_id="abc", caption="text")
        await collector.register_part(message=message, update_id=1)
        collector._cancel_timer(key=(123, "abc"))

        await collector._flush(chat_id=123, media_group_id="abc")

        assert await store.is_processed(chat_id=123, media_group_id="abc")
        assert await store.get(chat_id=123, media_group_id="abc") is None

    asyncio.run(_run())


def test_flush_not_committed_on_false(album_config: AlbumCollectorConfig) -> None:
    async def _run() -> None:
        async def on_flush(aggregated: AggregatedAlbum, message: Message) -> bool:
            return False

        collector, store = _setup_collector_for_flush(album_config, on_flush)
        message = _make_message(message_id=100, media_group_id="abc", caption="text")
        await collector.register_part(message=message, update_id=1)
        collector._cancel_timer(key=(123, "abc"))

        await collector._flush(chat_id=123, media_group_id="abc")

        assert not await store.is_processed(chat_id=123, media_group_id="abc")
        assert await store.get(chat_id=123, media_group_id="abc") is not None

    asyncio.run(_run())


def test_flush_not_committed_on_raise(album_config: AlbumCollectorConfig) -> None:
    async def _run() -> None:
        async def on_flush(aggregated: AggregatedAlbum, message: Message) -> bool:
            raise RuntimeError("flush failed")

        collector, store = _setup_collector_for_flush(album_config, on_flush)
        message = _make_message(message_id=100, media_group_id="abc", caption="text")
        await collector.register_part(message=message, update_id=1)
        collector._cancel_timer(key=(123, "abc"))

        try:
            await collector._flush(chat_id=123, media_group_id="abc")
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError")

        assert not await store.is_processed(chat_id=123, media_group_id="abc")
        assert await store.get(chat_id=123, media_group_id="abc") is not None

    asyncio.run(_run())
