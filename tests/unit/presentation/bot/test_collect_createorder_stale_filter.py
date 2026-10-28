from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from advertiser_blogger.presentation.bot.filters.collect_createorder_stale import (
    IsCollectCreateorderStaleCallback,
)
from advertiser_blogger.presentation.bot.states.collect_createorder import CollectCreateorderState


def test_stale_when_not_awaiting_accept() -> None:
    async def _run():
        filt = IsCollectCreateorderStaleCallback()
        callback = MagicMock(data="cco_accept")
        state = MagicMock()
        state.get_state = AsyncMock(return_value=CollectCreateorderState.awaiting_post.state)
        assert await filt(callback, state) is True

    asyncio.run(_run())


def test_not_stale_in_awaiting_accept() -> None:
    async def _run():
        filt = IsCollectCreateorderStaleCallback()
        callback = MagicMock(data="cco_accept")
        state = MagicMock()
        state.get_state = AsyncMock(return_value=CollectCreateorderState.awaiting_accept.state)
        assert await filt(callback, state) is False

    asyncio.run(_run())


def test_cancel_not_stale_in_awaiting_post() -> None:
    async def _run():
        filt = IsCollectCreateorderStaleCallback()
        callback = MagicMock(data="cco_cancel")
        state = MagicMock()
        state.get_state = AsyncMock(return_value=CollectCreateorderState.awaiting_post.state)
        assert await filt(callback, state) is False

    asyncio.run(_run())


def test_cancel_stale_when_collect_finished() -> None:
    async def _run():
        filt = IsCollectCreateorderStaleCallback()
        callback = MagicMock(data="cco_cancel")
        state = MagicMock()
        state.get_state = AsyncMock(return_value=None)
        assert await filt(callback, state) is True

    asyncio.run(_run())
