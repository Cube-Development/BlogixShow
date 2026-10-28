import asyncio
from uuid import uuid4

from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    BotPostDraft,
    BotProjectDraft,
    ChannelRefStatus,
)
from advertiser_blogger.presentation.bot.common.project_create_draft import (
    apply_channel_attach,
    can_bind_head_to_new_post,
    channel_mode_preview_action,
    enqueue_channel_batch,
    peek_channel_batch,
    peek_pending_channel_choice,
    pop_channel_batch,
    set_batch_awaiting_creative,
    set_channel_mode_waiting_callback,
)
from advertiser_blogger.presentation.bot.common.project_create_orphans import (
    create_empty_posts_for_channels,
)
from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard


class FakeFSM:
    def __init__(self) -> None:
        self._data: dict = {}

    async def get_data(self) -> dict:
        return dict(self._data)

    async def update_data(self, data: dict | None = None, **kwargs) -> None:
        payload = dict(data or {})
        payload.update(kwargs)
        self._data.update(payload)


def _ch(query: str) -> BotChannelRef:
    return BotChannelRef(
        status=ChannelRefStatus.found,
        query_raw=query,
        channel_id=uuid4(),
    )


def test_enqueue_two_batches_fifo() -> None:
    async def _run() -> None:
        state = FakeFSM()
        assert await peek_pending_channel_choice(state) is False
        show1 = await enqueue_channel_batch(
            state, text="@a @b", anchor_post_id="p1",
        )
        show2 = await enqueue_channel_batch(
            state, text="@c @d", anchor_post_id="p2",
        )
        assert show1 is True
        assert show2 is False
        head = await peek_channel_batch(state)
        assert head is not None
        assert head["text"] == "@a @b"
        assert head["anchor_post_id"] == "p1"
        assert head["awaiting_creative"] is False
        first = await pop_channel_batch(state)
        assert first["text"] == "@a @b"
        second = await peek_channel_batch(state)
        assert second is not None
        assert second["text"] == "@c @d"
        assert second["anchor_post_id"] == "p2"

    asyncio.run(_run())


def test_enqueue_same_anchor_stays_fifo() -> None:
    async def _run() -> None:
        state = FakeFSM()
        show1 = await enqueue_channel_batch(
            state, text="@a @b", anchor_post_id="p1",
        )
        show2 = await enqueue_channel_batch(
            state, text="@c @d", anchor_post_id="p1",
        )
        assert show1 is True
        assert show2 is False
        head = await peek_channel_batch(state)
        assert head is not None
        assert head["text"] == "@a @b"
        first = await pop_channel_batch(state)
        assert first["text"] == "@a @b"
        second = await peek_channel_batch(state)
        assert second is not None
        assert second["text"] == "@c @d"
        assert second["anchor_post_id"] == "p1"

    asyncio.run(_run())


def test_set_batch_awaiting_creative() -> None:
    async def _run() -> None:
        state = FakeFSM()
        await enqueue_channel_batch(state, text="@a", anchor_post_id="p1")
        assert await set_batch_awaiting_creative(state) is True
        head = await peek_channel_batch(state)
        assert head is not None
        assert head["awaiting_creative"] is True

    asyncio.run(_run())


def test_attach_to_above_uses_anchor_not_first_post() -> None:
    p1 = BotPostDraft(local_id="p1", text="a", channels=[_ch("@old")])
    p2 = BotPostDraft(local_id="p2", text="b", channels=[_ch("@x")])
    draft = BotProjectDraft(
        draft_id="d",
        user_id=uuid4(),
        telegram_id=1,
        posts=[p1, p2],
    )
    new_chs = [_ch("@y"), _ch("@z")]
    apply_channel_attach(draft, p2, new_chs, "attach")
    assert [c.query_raw for c in p1.channels] == ["@old"]
    assert [c.query_raw for c in p2.channels] == ["@x", "@y", "@z"]
    assert draft.common_post_id is None


def test_attach_to_above_sole_post_sets_common() -> None:
    p1 = BotPostDraft(local_id="p1", text="a", channels=[_ch("@old")])
    draft = BotProjectDraft(
        draft_id="d",
        user_id=uuid4(),
        telegram_id=1,
        posts=[p1],
        common_post_id="p1",
    )
    apply_channel_attach(draft, p1, [_ch("@extra")], "attach")
    assert len(p1.channels) == 2
    assert draft.common_post_id == "p1"


def test_leave_empty_batch_creates_empty_posts() -> None:
    draft = BotProjectDraft(
        draft_id="d",
        user_id=uuid4(),
        telegram_id=1,
        posts=[BotPostDraft(local_id="p1", channels=[_ch("@kept")])],
    )
    create_empty_posts_for_channels(draft, [_ch("@a"), _ch("@b")])
    assert len(draft.posts) == 3
    assert all(len(p.channels) == 1 for p in draft.posts)
    assert draft.common_post_id is None


def test_channel_mode_keyboard_callbacks() -> None:
    kb = InlineKeyboard().project_create_channel_mode_choice(
        to_above_text="above",
        own_creative_text="creative",
        leave_empty_text="empty",
    )
    assert [b.callback_data for row in kb.inline_keyboard for b in row] == [
        "pc_to_above",
        "pc_batch_creative",
        "pc_channel_leave_empty",
        "pc_cancel",
    ]


def test_same_anchor_fifo_p1_c1_c2_c3() -> None:
    async def _run() -> None:
        state = FakeFSM()
        assert await enqueue_channel_batch(
            state, text="https://t.me/c2", anchor_post_id="p1",
        ) is True
        assert await enqueue_channel_batch(
            state, text="https://t.me/c3", anchor_post_id="p1",
        ) is False
        head = await peek_channel_batch(state)
        assert head is not None
        assert head["text"] == "https://t.me/c2"
        rest = state._data["pc_pending_channel_choice"]
        assert [item["text"] for item in rest] == ["https://t.me/c2", "https://t.me/c3"]

    asyncio.run(_run())


def test_waiting_callback_new_post_does_not_steal_head() -> None:
    async def _run() -> None:
        state = FakeFSM()
        await enqueue_channel_batch(state, text="C2", anchor_post_id="p1")
        await enqueue_channel_batch(state, text="C3", anchor_post_id="p1")
        await set_channel_mode_waiting_callback(state, True)
        p_new = BotPostDraft(local_id="p_new", text="x")
        head = await peek_channel_batch(state)
        assert can_bind_head_to_new_post(head, p_new, newly_created=True) is False
        assert await channel_mode_preview_action(state) == "return"
        assert [item["text"] for item in state._data["pc_pending_channel_choice"]] == ["C2", "C3"]
        assert p_new.channels == []

    asyncio.run(_run())


def test_collect_waiting_callback_does_not_pop() -> None:
    async def _run() -> None:
        state = FakeFSM()
        await enqueue_channel_batch(state, text="C2", anchor_post_id="p1")
        await enqueue_channel_batch(state, text="C3", anchor_post_id="p1")
        head = await peek_channel_batch(state)
        p_new = BotPostDraft(local_id="p_new")
        assert head is not None
        assert head["awaiting_creative"] is False
        assert can_bind_head_to_new_post(head, p_new, newly_created=True) is False
        assert await peek_channel_batch(state) is not None
        assert (await peek_channel_batch(state))["text"] == "C2"

    asyncio.run(_run())


def test_waiting_creative_new_post_can_bind() -> None:
    async def _run() -> None:
        state = FakeFSM()
        await enqueue_channel_batch(state, text="C2", anchor_post_id="p1")
        await enqueue_channel_batch(state, text="C3", anchor_post_id="p1")
        assert await set_batch_awaiting_creative(state) is True
        p_new = BotPostDraft(local_id="p_new")
        head = await peek_channel_batch(state)
        assert can_bind_head_to_new_post(head, p_new, newly_created=True) is True
        popped = await pop_channel_batch(state)
        assert popped["text"] == "C2"
        nxt = await peek_channel_batch(state)
        assert nxt is not None
        assert nxt["text"] == "C3"
        await set_channel_mode_waiting_callback(state, False)
        assert await channel_mode_preview_action(state) == "show"

    asyncio.run(_run())


def test_waiting_creative_channel_only_does_not_pop_head() -> None:
    async def _run() -> None:
        state = FakeFSM()
        await enqueue_channel_batch(state, text="C2", anchor_post_id="p1")
        await enqueue_channel_batch(state, text="C3", anchor_post_id="p1")
        await set_batch_awaiting_creative(state)
        assert await enqueue_channel_batch(
            state, text="C_new", anchor_post_id="p1",
        ) is False
        head = await peek_channel_batch(state)
        assert head is not None
        assert head["text"] == "C2"
        assert head["awaiting_creative"] is True
        assert await channel_mode_preview_action(state) == "return"
        texts = [item["text"] for item in state._data["pc_pending_channel_choice"]]
        assert texts == ["C2", "C3", "C_new"]

    asyncio.run(_run())


def test_multiple_flush_does_not_reshow() -> None:
    async def _run() -> None:
        state = FakeFSM()
        await enqueue_channel_batch(state, text="C2", anchor_post_id="p1")
        assert await channel_mode_preview_action(state) == "show"
        await set_channel_mode_waiting_callback(state, True)
        await enqueue_channel_batch(state, text="C3", anchor_post_id="p1")
        assert await channel_mode_preview_action(state) == "return"
        await enqueue_channel_batch(state, text="C4", anchor_post_id="p1")
        assert await channel_mode_preview_action(state) == "return"
        texts = [item["text"] for item in state._data["pc_pending_channel_choice"]]
        assert texts == ["C2", "C3", "C4"]

    asyncio.run(_run())


def test_can_bind_rejects_existing_or_filled_post() -> None:
    head = {"text": "C2", "anchor_post_id": "p1", "awaiting_creative": True}
    filled = BotPostDraft(local_id="p_new", channels=[_ch("@x")])
    empty = BotPostDraft(local_id="p_new")
    assert can_bind_head_to_new_post(head, empty, newly_created=False) is False
    assert can_bind_head_to_new_post(head, filled, newly_created=True) is False
    assert can_bind_head_to_new_post(None, empty, newly_created=True) is False
    waiting_cb_head = {"text": "C2", "anchor_post_id": "p1", "awaiting_creative": False}
    assert can_bind_head_to_new_post(waiting_cb_head, empty, newly_created=True) is False
