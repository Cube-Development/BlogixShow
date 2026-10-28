from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from advertiser_blogger.application.interactors_bot.project_create.create_saved.dto import (
    CreateSavedProjectFromBotDraftInput,
)
from advertiser_blogger.application.interactors_bot.project_create.create_saved.use_case import (
    CreateSavedProjectFromBotDraft,
    DraftValidationError,
)
from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    BotPostDraft,
    BotProjectDraft,
    ChannelRefStatus,
)
from advertiser_blogger.application.interactors_bot.project_create.schedule import TASHKENT_TZ
from advertiser_blogger.domain.record.channel.constants import Format


def _draft_ok() -> BotProjectDraft:
    start = datetime.now(tz=TASHKENT_TZ) + timedelta(hours=2)
    end = start + timedelta(hours=2)
    return BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        project_name="Sale",
        comment="c",
        start_at=start,
        end_at=end,
        posts=[
            BotPostDraft(
                local_id="p1",
                text="hi",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@ch",
                        channel_id=uuid4(),
                        format=Format.telegram_1_24,
                    )
                ],
            )
        ],
    )


def _orch(**kwargs) -> CreateSavedProjectFromBotDraft:
    defaults = dict(
        fill_common_cart=AsyncMock(),
        create_project_from_cart=AsyncMock(
            return_value=MagicMock(project_id=uuid4(), orders=[]),
        ),
        create_post_custom_orders=MagicMock(),
        create_date_interval=MagicMock(),
        save_project=MagicMock(),
    )
    defaults.update(kwargs)
    return CreateSavedProjectFromBotDraft(**defaults)


def test_validate_rejects_unknown_channel():
    orch = _orch()
    draft = _draft_ok()
    draft.posts[0].channels[0].status = ChannelRefStatus.unknown
    with pytest.raises(DraftValidationError):
        orch.validate_draft(draft)


def test_validate_ok():
    _orch().validate_draft(_draft_ok())


def test_create_saved_uses_swap_comment_for_swap_post():
    import asyncio

    found_channel_id = uuid4()
    swap_a_id = uuid4()
    swap_b_id = uuid4()
    found_order_id = uuid4()
    swap_a_order_id = uuid4()
    swap_b_order_id = uuid4()
    project_id = uuid4()
    user_id = uuid4()

    start = datetime.now(tz=TASHKENT_TZ) + timedelta(hours=2)
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=user_id,
        telegram_id=1,
        comment="user comment",
        start_at=start,
        end_at=start + timedelta(hours=2),
        posts=[
            BotPostDraft(
                local_id="p1",
                text="hi",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@found",
                        channel_id=found_channel_id,
                        format=Format.telegram_1_24,
                    ),
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@missing_a",
                        channel_id=swap_a_id,
                        format=Format.telegram_1_24,
                        is_swap=True,
                    ),
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@missing_b",
                        channel_id=swap_b_id,
                        format=Format.telegram_1_24,
                        is_swap=True,
                        comment="note b",
                    ),
                ],
            )
        ],
    )

    create_post = AsyncMock()
    create_project = AsyncMock(
        return_value=MagicMock(
            project_id=project_id,
            orders=[
                MagicMock(id=found_order_id, channel_id=found_channel_id),
                MagicMock(id=swap_a_order_id, channel_id=swap_a_id),
                MagicMock(id=swap_b_order_id, channel_id=swap_b_id),
            ],
        )
    )

    orch = _orch(
        create_project_from_cart=create_project,
        create_post_custom_orders=create_post,
        create_date_interval=AsyncMock(),
        save_project=AsyncMock(),
        media_to_files=AsyncMock(return_value=[]),
    )

    result = asyncio.run(
        orch(CreateSavedProjectFromBotDraftInput(draft=draft, user_id=user_id))
    )
    assert result.partial is False
    assert create_post.await_count == 3

    found_call = create_post.await_args_list[0].kwargs["data"]
    swap_a_call = create_post.await_args_list[1].kwargs["data"]
    swap_b_call = create_post.await_args_list[2].kwargs["data"]
    assert found_call.comment == "user comment"
    assert found_call.orders == [found_order_id]
    assert "Заменить: @missing_a" in swap_a_call.comment
    assert "Комментарий: user comment" in swap_a_call.comment
    assert swap_a_call.orders == [swap_a_order_id]
    assert "Заменить: @missing_b" in swap_b_call.comment
    assert "note b" in swap_b_call.comment
    assert swap_b_call.orders == [swap_b_order_id]


def test_save_progress_orders_includes_empty_posts():
    import asyncio

    media_ch = uuid4()
    empty_ch = uuid4()
    media_order = uuid4()
    empty_order = uuid4()
    project_id = uuid4()
    user_id = uuid4()
    start = datetime.now(tz=TASHKENT_TZ) + timedelta(hours=2)
    from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import CreativeKind

    draft = BotProjectDraft(
        draft_id="d1",
        user_id=user_id,
        telegram_id=1,
        start_at=start,
        end_at=start + timedelta(hours=2),
        posts=[
            BotPostDraft(
                local_id="media",
                kind=CreativeKind.media,
                text="hi",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@media",
                        channel_id=media_ch,
                        format=Format.telegram_1_24,
                    )
                ],
            ),
            BotPostDraft(
                local_id="empty",
                kind=CreativeKind.empty,
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@empty",
                        channel_id=empty_ch,
                        format=Format.telegram_1_24,
                    )
                ],
            ),
        ],
    )
    events: list[tuple[str, int, int]] = []

    async def on_progress(phase: str, current: int, total: int) -> None:
        events.append((phase, current, total))

    create_post = AsyncMock()

    orch = _orch(
        create_project_from_cart=AsyncMock(
            return_value=MagicMock(
                project_id=project_id,
                orders=[
                    MagicMock(id=media_order, channel_id=media_ch),
                    MagicMock(id=empty_order, channel_id=empty_ch),
                ],
            )
        ),
        create_post_custom_orders=create_post,
        create_date_interval=AsyncMock(),
        save_project=AsyncMock(),
        media_to_files=AsyncMock(return_value=[]),
    )
    result = asyncio.run(
        orch(
            CreateSavedProjectFromBotDraftInput(
                draft=draft, user_id=user_id, on_progress=on_progress,
            )
        )
    )
    assert result.partial is False
    post_events = [e for e in events if e[0] == "posts"]
    assert post_events[0] == ("posts", 0, 2)
    assert ("posts", 1, 2) in post_events
    assert post_events[-1] == ("posts", 2, 2)


def test_save_continues_after_one_tz_post_fails():
    import asyncio

    ch_a = uuid4()
    ch_b = uuid4()
    order_a = uuid4()
    order_b = uuid4()
    project_id = uuid4()
    user_id = uuid4()
    start = datetime.now(tz=TASHKENT_TZ) + timedelta(hours=2)
    from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import CreativeKind

    draft = BotProjectDraft(
        draft_id="d1",
        user_id=user_id,
        telegram_id=1,
        start_at=start,
        end_at=start + timedelta(hours=2),
        posts=[
            BotPostDraft(
                local_id="fail",
                kind=CreativeKind.media,
                text="a",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@a",
                        channel_id=ch_a,
                        format=Format.telegram_1_24,
                    )
                ],
            ),
            BotPostDraft(
                local_id="ok",
                kind=CreativeKind.media,
                text="b",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@b",
                        channel_id=ch_b,
                        format=Format.telegram_1_24,
                    )
                ],
            ),
        ],
    )
    media = AsyncMock(side_effect=[RuntimeError("flood"), []])
    create_post = AsyncMock()
    save_project = AsyncMock()
    orch = _orch(
        create_project_from_cart=AsyncMock(
            return_value=MagicMock(
                project_id=project_id,
                orders=[
                    MagicMock(id=order_a, channel_id=ch_a),
                    MagicMock(id=order_b, channel_id=ch_b),
                ],
            )
        ),
        create_post_custom_orders=create_post,
        create_date_interval=AsyncMock(),
        save_project=save_project,
        media_to_files=media,
    )
    result = asyncio.run(
        orch(CreateSavedProjectFromBotDraftInput(draft=draft, user_id=user_id))
    )
    assert result.partial is True
    assert create_post.await_count == 1
    save_project.assert_awaited()
