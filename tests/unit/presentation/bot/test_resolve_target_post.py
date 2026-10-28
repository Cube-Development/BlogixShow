from uuid import uuid4

from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    BotPostDraft,
    BotProjectDraft,
    ChannelRefStatus,
    PublishMode,
)
from advertiser_blogger.domain.record.channel.constants import Format
from advertiser_blogger.presentation.bot.common.project_create_draft import (
    all_posts_have_channels,
    draft_ready_for_preview,
    has_post_waiting_for_channels,
    resolve_target_post,
    last_post_with_channels,
)


def _post(local_id: str, *, message_ids: list[int], channels: bool = False) -> BotPostDraft:
    ch = []
    if channels:
        ch = [
            BotChannelRef(
                status=ChannelRefStatus.found,
                query_raw="@ch",
                channel_id=uuid4(),
                format=Format.telegram_1_24,
            )
        ]
    return BotPostDraft(
        local_id=local_id,
        source_message_ids=message_ids,
        channels=ch,
    )


def test_resolve_target_post_by_reply_to() -> None:
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[
            _post("p1", message_ids=[10, 11]),
            _post("p2", message_ids=[20]),
        ],
        active_post_id="p2",
    )
    assert resolve_target_post(draft, reply_to_message_id=11).local_id == "p1"
    assert resolve_target_post(draft, reply_to_message_id=20).local_id == "p2"


def test_resolve_target_post_last_without_channels() -> None:
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[
            _post("p1", message_ids=[1], channels=True),
            _post("p2", message_ids=[2], channels=False),
        ],
        active_post_id="p1",
    )
    assert resolve_target_post(draft, reply_to_message_id=None).local_id == "p2"


def test_resolve_target_post_does_not_fall_back_to_bound_post() -> None:
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[
            _post("p1", message_ids=[1], channels=True),
            _post("p2", message_ids=[2], channels=True),
        ],
        active_post_id="p1",
    )
    assert resolve_target_post(draft, reply_to_message_id=None) is None
    assert resolve_target_post(draft, reply_to_message_id=1).local_id == "p1"


def test_last_post_with_channels() -> None:
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[
            _post("p1", message_ids=[1], channels=True),
            _post("p2", message_ids=[2], channels=False),
        ],
    )
    assert last_post_with_channels(draft).local_id == "p1"
    draft.posts[1].channels = draft.posts[0].channels
    assert last_post_with_channels(draft).local_id == "p2"


def test_append_post_idempotent_same_message_id() -> None:
    from types import SimpleNamespace

    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        append_post_from_message,
        new_draft,
    )
    from advertiser_blogger.domain.read.constants import Language

    user = SimpleNamespace(id=uuid4(), language=Language.ru)
    draft = new_draft(user=user, telegram_id=1)  # type: ignore[arg-type]
    msg = SimpleNamespace(
        message_id=42,
        text="hello",
        caption=None,
        photo=None,
        video=None,
        document=None,
        media_group_id=None,
    )
    p1 = append_post_from_message(draft, msg)  # type: ignore[arg-type]
    p2 = append_post_from_message(draft, msg)  # type: ignore[arg-type]
    assert p1.local_id == p2.local_id
    assert len(draft.posts) == 1
    assert draft.common_post_id == p1.local_id


def test_has_post_waiting_for_channels() -> None:
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[
            _post("p1", message_ids=[1], channels=True),
            _post("p2", message_ids=[2], channels=False),
        ],
    )
    assert has_post_waiting_for_channels(draft) is True
    assert all_posts_have_channels(draft) is False

    draft.posts[1].channels = draft.posts[0].channels
    assert has_post_waiting_for_channels(draft) is False
    assert all_posts_have_channels(draft) is True


def test_draft_ready_for_preview() -> None:
    from datetime import datetime, timedelta

    from advertiser_blogger.application.interactors_bot.project_create.schedule import TASHKENT_TZ

    start = datetime.now(tz=TASHKENT_TZ) + timedelta(hours=2)
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        start_at=start,
        end_at=start + timedelta(hours=2),
        posts=[_post("p1", message_ids=[1], channels=True)],
    )
    assert all_posts_have_channels(draft) is True
    assert draft_ready_for_preview(draft) is True

    draft.start_at = None
    assert draft_ready_for_preview(draft) is False

    draft.posts.append(_post("p2", message_ids=[2], channels=False))
    draft.start_at = start
    assert all_posts_have_channels(draft) is False
    assert draft_ready_for_preview(draft) is False


def test_attach_channels_one_to_one_clones_posts() -> None:
    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        attach_channels_one_to_one,
    )

    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[_post("p1", message_ids=[10, 11], channels=False)],
    )
    target = draft.posts[0]
    ch1 = BotChannelRef(status=ChannelRefStatus.found, query_raw="@a", channel_id=uuid4())
    ch2 = BotChannelRef(status=ChannelRefStatus.found, query_raw="@b", channel_id=uuid4())
    attached = attach_channels_one_to_one(draft, target, [ch1, ch2])
    assert len(attached) == 2
    assert len(draft.posts) == 2
    assert len(draft.posts[0].channels) == 1
    assert len(draft.posts[1].channels) == 1
    assert draft.posts[0].channels[0].query_raw == "@a"
    assert draft.posts[1].channels[0].query_raw == "@b"
    assert draft.posts[1].source_message_ids == [10, 11]
    assert draft.posts[0].local_id != draft.posts[1].local_id
    assert draft.common_post_id is None


def test_attach_multi_one_post_sets_common() -> None:
    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        apply_channel_attach,
        decide_channel_attach,
    )

    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[_post("p1", message_ids=[10], channels=False)],
    )
    target = draft.posts[0]
    ch1 = BotChannelRef(status=ChannelRefStatus.found, query_raw="@a", channel_id=uuid4())
    ch2 = BotChannelRef(status=ChannelRefStatus.found, query_raw="@b", channel_id=uuid4())
    mode = decide_channel_attach(draft, target, [ch1, ch2])
    assert mode == "attach"
    apply_channel_attach(draft, target, [ch1, ch2], mode)
    assert len(draft.posts) == 1
    assert [c.query_raw for c in draft.posts[0].channels] == ["@a", "@b"]
    assert draft.common_post_id == "p1"


def test_attach_multi_twice_no_conflict() -> None:
    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        apply_channel_attach,
        decide_channel_attach,
    )

    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[_post("p1", message_ids=[1], channels=False)],
    )
    ch1 = BotChannelRef(status=ChannelRefStatus.found, query_raw="@a", channel_id=uuid4())
    ch2 = BotChannelRef(status=ChannelRefStatus.found, query_raw="@b", channel_id=uuid4())
    apply_channel_attach(draft, draft.posts[0], [ch1, ch2], "attach")
    assert draft.common_post_id == "p1"

    draft.posts.append(_post("p2", message_ids=[2], channels=False))
    ch3 = BotChannelRef(status=ChannelRefStatus.found, query_raw="@c", channel_id=uuid4())
    ch4 = BotChannelRef(status=ChannelRefStatus.found, query_raw="@d", channel_id=uuid4())
    mode = decide_channel_attach(draft, draft.posts[1], [ch3, ch4])
    assert mode == "attach"
    apply_channel_attach(draft, draft.posts[1], [ch3, ch4], mode)
    assert len(draft.posts) == 2
    assert [c.query_raw for c in draft.posts[0].channels] == ["@a", "@b"]
    assert [c.query_raw for c in draft.posts[1].channels] == ["@c", "@d"]
    assert draft.common_post_id is None


def test_post_plus_one_channel_n_times() -> None:
    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        apply_channel_attach,
        sync_common_flag,
    )

    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[],
    )
    for idx in range(3):
        post = _post(f"p{idx}", message_ids=[idx + 1], channels=False)
        draft.posts.append(post)
        sync_common_flag(draft)
        ch = BotChannelRef(
            status=ChannelRefStatus.found,
            query_raw=f"@c{idx}",
            channel_id=uuid4(),
        )
        apply_channel_attach(draft, post, [ch], "attach")
    assert len(draft.posts) == 3
    assert all(len(p.channels) == 1 for p in draft.posts)
    assert draft.common_post_id is None


def test_second_post_clears_common() -> None:
    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        apply_channel_attach,
        sync_common_flag,
    )

    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[_post("p1", message_ids=[1], channels=False)],
    )
    ch1 = BotChannelRef(status=ChannelRefStatus.found, query_raw="@a", channel_id=uuid4())
    ch2 = BotChannelRef(status=ChannelRefStatus.found, query_raw="@b", channel_id=uuid4())
    apply_channel_attach(draft, draft.posts[0], [ch1, ch2], "attach")
    assert draft.common_post_id == "p1"
    assert len(draft.posts[0].channels) == 2

    draft.posts.append(_post("p2", message_ids=[2], channels=False))
    sync_common_flag(draft)
    assert draft.common_post_id is None
    assert [c.query_raw for c in draft.posts[0].channels] == ["@a", "@b"]


def test_ensure_does_not_split_multi() -> None:
    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        ensure_posts_channels_one_to_one,
    )

    post = _post("p1", message_ids=[1], channels=False)
    post.channels = [
        BotChannelRef(status=ChannelRefStatus.found, query_raw="@a", channel_id=uuid4()),
        BotChannelRef(status=ChannelRefStatus.found, query_raw="@b", channel_id=uuid4()),
        BotChannelRef(status=ChannelRefStatus.found, query_raw="@c", channel_id=uuid4()),
    ]
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[post],
    )
    ensure_posts_channels_one_to_one(draft)
    assert len(draft.posts) == 1
    assert len(draft.posts[0].channels) == 3
    assert draft.common_post_id == "p1"


def test_ensure_keeps_multi_on_unique_posts() -> None:
    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        ensure_posts_channels_one_to_one,
    )

    p1 = _post("p1", message_ids=[1], channels=False)
    p1.channels = [
        BotChannelRef(status=ChannelRefStatus.found, query_raw="@a", channel_id=uuid4()),
        BotChannelRef(status=ChannelRefStatus.found, query_raw="@b", channel_id=uuid4()),
    ]
    p2 = _post("p2", message_ids=[2], channels=False)
    p2.channels = [
        BotChannelRef(status=ChannelRefStatus.found, query_raw="@c", channel_id=uuid4()),
        BotChannelRef(status=ChannelRefStatus.found, query_raw="@d", channel_id=uuid4()),
    ]
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[p1, p2],
        common_post_id="p1",
    )
    ensure_posts_channels_one_to_one(draft)
    assert len(draft.posts) == 2
    assert len(draft.posts[0].channels) == 2
    assert len(draft.posts[1].channels) == 2
    assert draft.common_post_id is None


def test_common_post_id_roundtrip() -> None:
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        common_post_id="p1",
        posts=[_post("p1", message_ids=[1], channels=True)],
    )
    restored = BotProjectDraft.from_dict(draft.to_dict())
    assert restored.common_post_id == "p1"
    assert restored.publish_mode is PublishMode.forward


def test_publish_mode_roundtrip_and_legacy_default() -> None:
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        publish_mode=PublishMode.copy,
        posts=[_post("p1", message_ids=[1])],
    )
    restored = BotProjectDraft.from_dict(draft.to_dict())
    assert restored.publish_mode is PublishMode.copy

    payload = draft.to_dict()
    del payload["publish_mode"]
    legacy = BotProjectDraft.from_dict(payload)
    assert legacy.publish_mode is PublishMode.forward


def test_remove_post_syncs_common() -> None:
    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        remove_post_from_draft,
    )

    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        common_post_id="p1",
        posts=[
            _post("p1", message_ids=[1], channels=True),
            _post("p2", message_ids=[2], channels=True),
        ],
    )
    remove_post_from_draft(draft, "p1")
    assert draft.common_post_id == "p2"
    assert [p.local_id for p in draft.posts] == ["p2"]


def test_replace_post_content_from_album() -> None:
    from types import SimpleNamespace

    from advertiser_blogger.presentation.bot.common.project_create_draft import (
        replace_post_content_from_album,
    )

    post = _post("p1", message_ids=[1], channels=True)
    aggregated = SimpleNamespace(
        media_group_id="mg-1",
        parts=[
            SimpleNamespace(
                media_type="photo",
                file_id="f1",
                caption="slide 1",
                message_id=101,
            ),
            SimpleNamespace(
                media_type="photo",
                file_id="f2",
                caption=None,
                message_id=102,
            ),
        ],
    )
    replace_post_content_from_album(post, aggregated)
    assert post.media_group_id == "mg-1"
    assert post.source_message_ids == [101, 102]
    assert post.text == "slide 1"
    assert len(post.media) == 2
    assert len(post.channels) == 1


def test_project_create_channel_menu_grid() -> None:
    from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard

    kb = InlineKeyboard().project_create_channel_menu(3)
    rows = kb.inline_keyboard
    assert len(rows) == 5
    assert [b.callback_data for b in rows[0]] == ["pc_show_post:3", "pc_replace_post:3"]
    assert [b.callback_data for b in rows[1]] == ["pc_reset_time:3", "pc_edit_time:3"]
    assert [b.callback_data for b in rows[2]] == ["pc_reset_comment:3", "pc_edit_comment:3"]
    assert [b.callback_data for b in rows[3]] == ["pc_delete:3", "pc_replace:3"]
    assert [b.callback_data for b in rows[4]] == ["pc_back"]


def test_channel_mode_keyboard_three_buttons() -> None:
    from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard

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
