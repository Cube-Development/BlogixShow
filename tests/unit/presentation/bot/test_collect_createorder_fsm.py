from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from advertiser_blogger.presentation.bot.common.collect_createorder_fsm import chat_accept_lock
from advertiser_blogger.presentation.bot.handlers.user.collect_createorder import _safe_callback_answer


def test_chat_accept_lock_serializes_same_chat() -> None:
    async def _run():
        lock = chat_accept_lock(42)
        assert not lock.locked()
        await lock.acquire()
        assert lock.locked()
        assert chat_accept_lock(42) is lock
        lock.release()

    asyncio.run(_run())


def test_safe_callback_answer_swallows_errors() -> None:
    async def _run():
        callback = MagicMock()
        callback.answer = AsyncMock(side_effect=RuntimeError("telegram down"))
        await _safe_callback_answer(callback, "hi")

    asyncio.run(_run())
