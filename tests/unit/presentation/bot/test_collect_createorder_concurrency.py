from __future__ import annotations

import asyncio

from advertiser_blogger.presentation.bot.common.collect_createorder_fsm import (
    chat_accept_lock,
    collect_chat_mutations_lock,
)


def test_replace_waits_until_accept_finishes() -> None:
    async def _run():
        chat_id = 7001
        order: list[str] = []

        async def accept_like() -> None:
            async with collect_chat_mutations_lock(chat_id):
                order.append("accept_start")
                await asyncio.sleep(0.05)
                order.append("accept_end")

        async def replace_like() -> None:
            await asyncio.sleep(0.01)
            async with collect_chat_mutations_lock(chat_id):
                order.append("replace")

        await asyncio.gather(accept_like(), replace_like())
        assert order == ["accept_start", "accept_end", "replace"]

    asyncio.run(_run())


def test_new_post_waits_until_accept_finishes() -> None:
    async def _run():
        chat_id = 7002
        order: list[str] = []

        async def accept_like() -> None:
            async with collect_chat_mutations_lock(chat_id):
                order.append("accept_start")
                await asyncio.sleep(0.05)
                order.append("accept_end")

        async def new_post_like() -> None:
            await asyncio.sleep(0.01)
            async with collect_chat_mutations_lock(chat_id):
                order.append("new_post")

        await asyncio.gather(accept_like(), new_post_like())
        assert order == ["accept_start", "accept_end", "new_post"]

    asyncio.run(_run())


def test_accept_uses_same_lock_as_mutations_helper() -> None:
    chat_id = 7003
    assert chat_accept_lock(chat_id) is chat_accept_lock(chat_id)
