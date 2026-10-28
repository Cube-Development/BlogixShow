from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from configuration.common import MessageBatchCollectorConfig
from advertiser_blogger.presentation.bot.message_batch.collector import MessageBatchCollector
from advertiser_blogger.presentation.bot.message_batch.models import MessageBatch, RegisterResult
from advertiser_blogger.presentation.bot.message_batch.middleware import _should_buffer_message
from advertiser_blogger.presentation.bot.message_batch.pairing_fsm import (
    PairingActionKind,
    PairingState,
    ProjectCreatePairingFSM,
    classify_message,
    PairingEvent,
)


def _msg(
        message_id: int,
        *,
        text: str | None = None,
        photo: bool = False,
        chat_id: int = 1,
) -> MagicMock:
    message = MagicMock()
    message.message_id = message_id
    message.chat.id = chat_id
    message.text = text
    message.caption = None
    message.media_group_id = None
    message.photo = [SimpleNamespace(file_id="p")] if photo else None
    message.video = None
    message.document = None
    message.animation = None
    message.reply_to_message = None
    message.from_user = SimpleNamespace(id=42)
    return message


def test_collector_sorts_by_message_id_on_flush() -> None:
    async def _run() -> None:
        flushed: list[MessageBatch] = []

        async def on_flush(batch: MessageBatch) -> bool:
            flushed.append(batch)
            return True

        collector = MessageBatchCollector(
            config=MessageBatchCollectorConfig(debounce_ms=20, max_items=40, max_batch_age_ms=5000),
            on_flush=on_flush,
        )
        await collector.register(_msg(7044, photo=True))
        await collector.register(_msg(7038, photo=True))
        await collector.register(_msg(7039, text="https://t.me/channelone"))
        await asyncio.sleep(0.05)
        assert len(flushed) == 1
        assert [m.message_id for m in flushed[0].messages] == [7038, 7039, 7044]
        assert flushed[0].received_count == 3

    asyncio.run(_run())


def test_collector_flushes_on_max_items() -> None:
    async def _run() -> None:
        flushed: list[MessageBatch] = []

        async def on_flush(batch: MessageBatch) -> bool:
            flushed.append(batch)
            return True

        collector = MessageBatchCollector(
            config=MessageBatchCollectorConfig(debounce_ms=10_000, max_items=3, max_batch_age_ms=60_000),
            on_flush=on_flush,
        )
        assert await collector.register(_msg(1, photo=True)) == RegisterResult.FIRST
        assert await collector.register(_msg(2, photo=True)) == RegisterResult.PENDING
        assert await collector.register(_msg(3, photo=True)) == RegisterResult.FLUSH_SCHEDULED
        await asyncio.sleep(0.02)
        assert len(flushed) == 1
        assert flushed[0].received_count == 3

    asyncio.run(_run())


def test_collector_concurrent_register_one_first() -> None:
    async def _run() -> None:
        collector = MessageBatchCollector(
            config=MessageBatchCollectorConfig(
                debounce_ms=10_000, max_items=40, max_batch_age_ms=60_000,
            ),
            on_flush=AsyncMock(return_value=True),
        )
        results = await asyncio.gather(*[
            collector.register(_msg(i, photo=True)) for i in range(1, 21)
        ])
        assert results.count(RegisterResult.FIRST) == 1
        assert results.count(RegisterResult.PENDING) == 19

    asyncio.run(_run())


def test_collector_flushes_on_max_batch_age() -> None:
    async def _run() -> None:
        flushed: list[MessageBatch] = []

        async def on_flush(batch: MessageBatch) -> bool:
            flushed.append(batch)
            return True

        collector = MessageBatchCollector(
            config=MessageBatchCollectorConfig(debounce_ms=10_000, max_items=40, max_batch_age_ms=40),
            on_flush=on_flush,
        )
        await collector.register(_msg(10, photo=True))
        # Keep resetting debounce with continuous stream; age should still flush.
        await collector.register(_msg(11, text="https://t.me/channela"))
        await asyncio.sleep(0.02)
        await collector.register(_msg(12, photo=True))
        await asyncio.sleep(0.05)
        assert len(flushed) >= 1
        assert flushed[0].messages[0].message_id == 10

    asyncio.run(_run())


def test_should_buffer_filters() -> None:
    assert _should_buffer_message(_msg(1, photo=True), "ProjectCreateState:awaiting_post") is True
    assert _should_buffer_message(_msg(1, text="Отмена"), "ProjectCreateState:awaiting_post") is False
    assert _should_buffer_message(_msg(1, text="/start"), "ProjectCreateState:awaiting_post") is False
    assert _should_buffer_message(_msg(1, photo=True), None) is False
    assert _should_buffer_message(
        _msg(1, photo=True), "ProjectCreateState:awaiting_replace_post",
    ) is False
    assert _should_buffer_message(
        _msg(1, text="@ch"), "ProjectCreateState:awaiting_replace",
    ) is False
    mg = _msg(1, photo=True)
    mg.media_group_id = "abc"
    assert _should_buffer_message(mg, "ProjectCreateState:awaiting_post") is False


def test_pairing_fsm_media_link_pairs() -> None:
    fsm = ProjectCreatePairingFSM()
    m1 = _msg(1, photo=True)
    m2 = _msg(2, text="https://t.me/channelone")
    m3 = _msg(3, photo=True)
    m4 = _msg(4, text="https://t.me/channeltwo")

    a1 = fsm.on_message(m1)
    assert a1[0].kind is PairingActionKind.CREATE_POST
    assert fsm.state is PairingState.WAITING_CHANNEL

    a2 = fsm.on_message(m2)
    assert a2[0].kind is PairingActionKind.BIND_CHANNEL
    assert a2[0].bind_to_message_id == 1
    assert fsm.state is PairingState.IDLE

    a3 = fsm.on_message(m3)
    assert a3[0].kind is PairingActionKind.CREATE_POST
    a4 = fsm.on_message(m4)
    assert a4[0].kind is PairingActionKind.BIND_CHANNEL
    assert a4[0].bind_to_message_id == 3


def test_pairing_fsm_reply_to_binds_when_idle() -> None:
    fsm = ProjectCreatePairingFSM()
    link = _msg(2, text="https://t.me/channelone")
    link.reply_to_message = SimpleNamespace(message_id=1)
    actions = fsm.on_message(link)
    assert actions[0].kind is PairingActionKind.BIND_CHANNEL
    assert actions[0].bind_to_message_id == 1
    assert fsm.state is PairingState.IDLE


def test_pairing_fsm_media_media_leaves_first_waiting() -> None:
    fsm = ProjectCreatePairingFSM()
    a1 = fsm.on_message(_msg(1, photo=True))
    assert a1[0].kind is PairingActionKind.CREATE_POST
    a2 = fsm.on_message(_msg(2, photo=True))
    assert a2[0].kind is PairingActionKind.CREATE_POST
    assert fsm.waiting_post_message_id == 2
    a3 = fsm.on_message(_msg(3, text="https://t.me/onlychan"))
    assert a3[0].kind is PairingActionKind.BIND_CHANNEL
    assert a3[0].bind_to_message_id == 2


def test_classify_channel_only() -> None:
    assert classify_message(_msg(1, photo=True)) is PairingEvent.MEDIA
    assert classify_message(_msg(2, text="https://t.me/channelx")) is PairingEvent.CHANNEL_ONLY
    assert classify_message(_msg(3, text="Проект: Test\nhttps://t.me/channelx")) is PairingEvent.RICH_METADATA
