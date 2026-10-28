import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    BotPostDraft,
    BotProjectDraft,
    ChannelRefStatus,
)
from advertiser_blogger.domain.record.channel.constants import Format
from advertiser_blogger.presentation.bot.common.project_create_draft import (
    PENDING_METADATA_KEY,
    stash_pending_metadata,
)
from advertiser_blogger.presentation.bot.common.project_create_orphans import (
    fill_orphans_leave_empty,
    pair_orphan_posts_with_channels,
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


def _ch(query: str, *, is_swap: bool = False) -> BotChannelRef:
    return BotChannelRef(
        status=ChannelRefStatus.found,
        query_raw=query,
        channel_id=uuid4(),
        display_name=query,
        url=f"https://t.me/{query.lstrip('@')}",
        format=Format.telegram_1_24,
        is_swap=is_swap,
    )


def test_pair_orphan_posts_extra_channels_become_common() -> None:
    creative = BotPostDraft(local_id="creative", text="ad", source_message_ids=[1])
    draft = BotProjectDraft(
        draft_id="d",
        user_id=uuid4(),
        telegram_id=1,
        posts=[creative],
    )
    ch1 = _ch("@a")
    ch2 = _ch("@b")
    leftover = pair_orphan_posts_with_channels(draft, [ch1, ch2])
    assert leftover == []
    assert creative.channels == [ch1, ch2]
    assert len(draft.posts) == 1
    assert draft.common_post_id == "creative"


def test_leave_empty_pairs_pending_channels_to_orphan_post() -> None:
    async def _run() -> None:
        state = FakeFSM()
        await stash_pending_metadata(
            state,
            "https://t.me/headlines_for_traders\nhttps://t.me/ru2ch",
        )
        creative = BotPostDraft(local_id="creative", text="ad", source_message_ids=[1])
        draft = BotProjectDraft(
            draft_id="d",
            user_id=uuid4(),
            telegram_id=1,
            posts=[
                BotPostDraft(local_id="kept", channels=[_ch("@already")]),
                creative,
            ],
        )

        ch1 = _ch("@headlines_for_traders")
        ch2 = _ch("@ru2ch")
        resolve = SimpleNamespace(
            resolve_many=AsyncMock(return_value=[ch1, ch2]),
            allocate_free_swaps=AsyncMock(return_value=[]),
        )
        config = SimpleNamespace(
            bot_project=SimpleNamespace(
                timezone="Asia/Tashkent",
                default_duration_hours=2,
                slot_minutes=5,
            ),
        )

        filled = await fill_orphans_leave_empty(
            state=state,
            draft=draft,
            resolve_channels=resolve,
            config=config,
        )
        assert filled is True
        assert state._data.get(PENDING_METADATA_KEY) in (None, [])
        assert creative.channels == [ch1]
        assert draft.common_post_id is None
        assert len(draft.posts) == 3
        assert draft.posts[2].channels[0].query_raw == "@ru2ch"
        resolve.allocate_free_swaps.assert_not_called()

    asyncio.run(_run())


def test_pair_orphan_leftover_when_other_posts_exist() -> None:
    creative = BotPostDraft(local_id="creative", text="ad", source_message_ids=[1])
    draft = BotProjectDraft(
        draft_id="d",
        user_id=uuid4(),
        telegram_id=1,
        posts=[
            BotPostDraft(local_id="kept", channels=[_ch("@already")]),
            creative,
        ],
    )
    leftover = pair_orphan_posts_with_channels(draft, [_ch("@a"), _ch("@b")])
    assert creative.channels[0].query_raw == "@a"
    assert len(leftover) == 1
    assert leftover[0].query_raw == "@b"
    assert draft.common_post_id is None


def test_leave_empty_swap_only_when_no_pending() -> None:
    async def _run() -> None:
        state = FakeFSM()
        orphan = BotPostDraft(local_id="orphan", text="solo")
        draft = BotProjectDraft(
            draft_id="d",
            user_id=uuid4(),
            telegram_id=1,
            posts=[orphan],
        )
        swap = _ch("EMPTY", is_swap=True)
        swap.url = "https://t.me/channel_swap1"
        resolve = SimpleNamespace(
            resolve_many=AsyncMock(return_value=[]),
            allocate_free_swaps=AsyncMock(return_value=[swap]),
        )
        config = SimpleNamespace(
            bot_project=SimpleNamespace(
                timezone="Asia/Tashkent",
                default_duration_hours=2,
                slot_minutes=5,
            ),
        )
        filled = await fill_orphans_leave_empty(
            state=state,
            draft=draft,
            resolve_channels=resolve,
            config=config,
        )
        assert filled is True
        assert orphan.channels == [swap]
        resolve.allocate_free_swaps.assert_called_once()

    asyncio.run(_run())
