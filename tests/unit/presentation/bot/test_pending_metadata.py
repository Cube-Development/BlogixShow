import asyncio

from advertiser_blogger.presentation.bot.common.project_create_draft import (
    PENDING_BY_REPLY_TO_KEY,
    PENDING_METADATA_KEY,
    clear_pending_metadata,
    peek_pending_metadata,
    pop_pending_by_reply_to_ids,
    pop_pending_metadata,
    stash_pending_by_reply_to,
    stash_pending_metadata,
)

class FakeFSM:
    def __init__(self) -> None:
        self._data: dict = {}

    async def get_data(self) -> dict:
        return dict(self._data)

    async def update_data(self, data: dict | None = None, **kwargs) -> None:
        payload = dict(data or {})
        payload.update(kwargs)
        self._data.update(payload)


def test_stash_pop_pending_metadata() -> None:
    async def _run() -> None:
        state = FakeFSM()
        meta = "@channel\n01.01.2026 12:00"

        await stash_pending_metadata(state, meta)
        assert state._data[PENDING_METADATA_KEY] == [meta]

        pending = await pop_pending_metadata(state)
        assert pending == meta
        assert await pop_pending_metadata(state) is None

    asyncio.run(_run())


def test_stash_queues_fifo_and_clear() -> None:
    async def _run() -> None:
        state = FakeFSM()
        await stash_pending_metadata(state, "first")
        await stash_pending_metadata(state, "second")
        assert state._data[PENDING_METADATA_KEY] == ["first", "second"]
        assert await peek_pending_metadata(state) is True

        assert await pop_pending_metadata(state) == "first"
        assert await pop_pending_metadata(state) == "second"
        assert await peek_pending_metadata(state) is False

        await stash_pending_metadata(state, "again")
        await clear_pending_metadata(state)
        assert await pop_pending_metadata(state) is None

    asyncio.run(_run())


def test_metadata_before_post_then_apply_flow() -> None:
    """Metadata without posts is stashed; after album flush / creative, pending is popped."""

    async def _run() -> None:
        state = FakeFSM()
        posts: list = []

        meta = (
            "Проект: Название РК\n"
            "Комментарий: test\n"
            "Время: завтра 17:00 - 19:00\n"
            "Каналы:\n@channel_one"
        )
        if not posts:
            await stash_pending_metadata(state, meta)

        # album flush / creative saved
        posts.append({"id": "creative"})
        pending = await pop_pending_metadata(state)
        assert pending == meta
        assert posts

    asyncio.run(_run())


def test_pop_legacy_string_pending() -> None:
    async def _run() -> None:
        state = FakeFSM()
        state._data[PENDING_METADATA_KEY] = "@legacy"
        assert await pop_pending_metadata(state) == "@legacy"
        assert await pop_pending_metadata(state) is None

    asyncio.run(_run())


def test_stash_pop_pending_by_reply_to() -> None:
    async def _run() -> None:
        state = FakeFSM()
        await stash_pending_by_reply_to(state, 101, "@ch1\nПроект: A")
        await stash_pending_by_reply_to(state, 102, "@ch2")
        assert state._data[PENDING_BY_REPLY_TO_KEY]["101"] == "@ch1\nПроект: A"

        found = await pop_pending_by_reply_to_ids(state, [101, 999])
        assert found == [(101, "@ch1\nПроект: A")]
        assert "101" not in state._data[PENDING_BY_REPLY_TO_KEY]
        assert "102" in state._data[PENDING_BY_REPLY_TO_KEY]

        found2 = await pop_pending_by_reply_to_ids(state, [102])
        assert found2 == [(102, "@ch2")]
        assert await pop_pending_by_reply_to_ids(state, [102]) == []

        await stash_pending_by_reply_to(state, 103, "x")
        await clear_pending_metadata(state)
        assert state._data[PENDING_BY_REPLY_TO_KEY] == {}
        assert await pop_pending_metadata(state) is None

    asyncio.run(_run())


def test_remove_orphan_post_from_draft() -> None:
    from uuid import uuid4

    from advertiser_blogger.application.interactors_bot.project_create.models import (
        BotChannelRef,
        BotPostDraft,
        BotProjectDraft,
        ChannelRefStatus,
    )
    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        has_post_waiting_for_channels,
        remove_post_from_draft,
    )

    kept = BotPostDraft(
        local_id="kept",
        text="a",
        channels=[
            BotChannelRef(status=ChannelRefStatus.found, query_raw="@ch1", channel_id=uuid4()),
        ],
    )
    orphan = BotPostDraft(local_id="orphan", text="b")
    draft = BotProjectDraft(
        draft_id="d",
        user_id=uuid4(),
        telegram_id=1,
        posts=[kept, orphan],
        active_post_id="orphan",
    )
    assert has_post_waiting_for_channels(draft) is True
    assert remove_post_from_draft(draft, "orphan") is True
    assert [p.local_id for p in draft.posts] == ["kept"]
    assert draft.active_post_id == "kept"
    assert has_post_waiting_for_channels(draft) is False
    assert remove_post_from_draft(draft, "missing") is False
