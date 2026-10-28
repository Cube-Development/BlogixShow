from datetime import datetime, timedelta
from uuid import uuid4

from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import CreativeKind
from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    BotPostDraft,
    BotProjectDraft,
    ChannelRefStatus,
    ScheduleSource,
)
from advertiser_blogger.application.interactors_bot.project_create.schedule import TASHKENT_TZ
from advertiser_blogger.domain.read.constants import Language
from advertiser_blogger.domain.record.channel.constants import Format
from advertiser_blogger.presentation.bot.common.project_create_texts import (
    build_ask_project_tz,
    build_channel_detail_text,
    build_channel_mode_ask_creative_text,
    build_channel_mode_prompt_text,
    build_confirm_progress_text,
    build_create_order_url,
    build_orphan_prompt_text,
    build_preview_text,
    channel_comment_for_display,
    channel_comment_for_order,
    confirm_progress_bar,
    draft_can_confirm,
    draft_missing_project_tz_fields,
)


def _draft_with_channel(status: ChannelRefStatus) -> BotProjectDraft:
    start = datetime.now(tz=TASHKENT_TZ) + timedelta(hours=2)
    return BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        start_at=start,
        end_at=start + timedelta(hours=2),
        posts=[
            BotPostDraft(
                local_id="p1",
                channels=[
                    BotChannelRef(
                        status=status,
                        query_raw="@ch",
                        channel_id=uuid4() if status == ChannelRefStatus.found else None,
                        format=Format.telegram_1_24 if status == ChannelRefStatus.found else None,
                    )
                ],
            )
        ],
    )


def test_draft_can_confirm_only_when_all_channels_found() -> None:
    assert draft_can_confirm(_draft_with_channel(ChannelRefStatus.found)) is True
    assert draft_can_confirm(_draft_with_channel(ChannelRefStatus.unknown)) is False
    assert draft_can_confirm(_draft_with_channel(ChannelRefStatus.invalid)) is False


def test_build_create_order_url() -> None:
    project_id = uuid4()
    assert build_create_order_url(
        frontend_domain="https://blogix.uz",
        project_id=project_id,
    ) == f"https://blogix.uz/createorder?project_id={project_id}"


def test_build_create_order_url_strips_trailing_slash() -> None:
    project_id = uuid4()
    assert build_create_order_url(
        frontend_domain="https://blogix.uz/",
        project_id=project_id,
    ) == f"https://blogix.uz/createorder?project_id={project_id}"


def test_build_preview_text_includes_banner() -> None:
    text = build_preview_text(
        _draft_with_channel(ChannelRefStatus.unknown),
        Language.ru,
        banner="Fix channels",
    )
    assert text.startswith("⚠ Fix channels")
    assert "Превью проекта" in text
    assert "✅ Найдено: 0" in text
    assert "⚠ Не найдено: 1" in text
    assert "Пустые каналы: 0" in text


def test_build_preview_text_schedule_and_comment_per_channel() -> None:
    start = datetime(2026, 7, 17, 17, 0, tzinfo=TASHKENT_TZ)
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        project_name="Название РК",
        comment="что угодно",
        start_at=start,
        end_at=start + timedelta(hours=2),
        schedule_source=ScheduleSource.user_defined,
        posts=[
            BotPostDraft(
                local_id="p1",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@real",
                        channel_id=uuid4(),
                        display_name="Real Channel",
                        url="https://t.me/real",
                        format=Format.telegram_1_24,
                    ),
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@missing",
                        channel_id=uuid4(),
                        display_name="Blogix | Канал на замену",
                        url="https://t.me/blogix_swap_channel",
                        format=Format.telegram_1_24,
                        is_swap=True,
                    ),
                ],
            )
        ],
    )
    text = build_preview_text(draft, Language.ru)
    assert "Проект: Название РК" in text
    assert "✅ Найдено: 1" in text
    assert "⚠ Не найдено: 1" in text
    assert "Пустые каналы: 0" in text
    assert "Пост: Есть" in text
    assert "Пост: 🔹Пусто" not in text
    assert "\nДата:" not in text
    assert "Начало:" not in text
    assert "Окончание:" not in text
    assert text.count("17.07.2026 · 17:00–19:00") == 2
    assert text.count("Коммент: что угодно") == 2
    assert "✅ [1] Real Channel (https://t.me/real)" in text
    assert (
        "⚠ [2] Blogix | Канал на замену (https://t.me/blogix_swap_channel) "
        "(вместо @missing)"
    ) in text
    assert draft_can_confirm(draft) is True


def test_build_preview_text_marks_empty_post_channels() -> None:
    start = datetime.now(tz=TASHKENT_TZ) + timedelta(hours=2)
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        start_at=start,
        end_at=start + timedelta(hours=2),
        posts=[
            BotPostDraft(
                local_id="empty",
                kind=CreativeKind.empty,
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@empty",
                        channel_id=uuid4(),
                        display_name="EmptyCh",
                        url="https://t.me/empty",
                        format=Format.telegram_1_24,
                    )
                ],
            )
        ],
    )
    text = build_preview_text(draft, Language.ru)
    assert "Пустые каналы: 1" in text
    assert "Пост: 🔹Пусто" in text
    assert "Пост: Есть" not in text


def test_build_preview_text_paginates_channels() -> None:
    start = datetime(2026, 7, 17, 17, 0, tzinfo=TASHKENT_TZ)
    channels = [
        BotChannelRef(
            status=ChannelRefStatus.found,
            query_raw=f"@ch{i}",
            channel_id=uuid4(),
            display_name=f"Ch{i}",
            url=f"https://t.me/ch{i}",
            format=Format.telegram_1_24,
        )
        for i in range(1, 6)
    ]
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        project_name="RK",
        start_at=start,
        end_at=start + timedelta(hours=2),
        posts=[BotPostDraft(local_id="p1", channels=channels)],
    )
    page1 = build_preview_text(draft, Language.ru, page=1, page_size=2)
    assert "Стр. 1/3" in page1
    assert "✅ [1] Ch1" in page1
    assert "✅ [2] Ch2" in page1
    assert "Ch3" not in page1

    page2 = build_preview_text(draft, Language.ru, page=2, page_size=2)
    assert "Стр. 2/3" in page2
    assert "✅ [3] Ch3" in page2
    assert "✅ [4] Ch4" in page2
    assert "Ch1 (" not in page2

    page3 = build_preview_text(draft, Language.ru, page=3, page_size=2)
    assert "Стр. 3/3" in page3
    assert "✅ [5] Ch5" in page3
    assert "✅ Найдено: 5" in page3
    assert "⚠ Не найдено: 0" in page3


def test_build_preview_text_marks_swap_channel() -> None:
    start = datetime.now(tz=TASHKENT_TZ) + timedelta(hours=2)
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        start_at=start,
        end_at=start + timedelta(hours=2),
        posts=[
            BotPostDraft(
                local_id="p1",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@missing",
                        channel_id=uuid4(),
                        display_name="Blogix | Канал на замену",
                        url="https://t.me/blogix_swap_channel",
                        format=Format.telegram_1_24,
                        is_swap=True,
                        comment="любое время завтра",
                        start_at=start + timedelta(days=1),
                        end_at=start + timedelta(days=1, hours=2),
                    )
                ],
            )
        ],
    )
    text = build_preview_text(draft, Language.ru)
    assert (
        "⚠ [1] Blogix | Канал на замену (https://t.me/blogix_swap_channel) "
        "(вместо @missing)"
    ) in text
    assert "Коммент: любое время завтра" in text
    assert "комментарий -" not in text.lower()
    assert draft_can_confirm(draft) is True


def test_build_channel_detail_text_full_template() -> None:
    start = datetime(2026, 7, 21, 18, 40, tzinfo=TASHKENT_TZ)
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        comment="общий коммент",
        start_at=start,
        end_at=start + timedelta(hours=2),
        posts=[
            BotPostDraft(
                local_id="p1",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="https://t.me/FaxriddinTuropov2",
                        channel_id=uuid4(),
                        display_name="ChannelSwap1",
                        url="https://t.me/channel_swap1",
                        format=Format.telegram_1_24,
                        is_swap=True,
                        comment="срочный",
                        start_at=start,
                        end_at=start + timedelta(hours=2),
                        schedule_source=ScheduleSource.user_defined,
                    )
                ],
            )
        ],
    )
    text = build_channel_detail_text(draft.posts[0].channels[0], 4, draft, Language.ru)
    assert "Канал #4" in text
    assert "Название: ChannelSwap1" in text
    assert "Ссылка: https://t.me/channel_swap1" in text
    assert "Дата: 21.07.2026" in text
    assert "Время: 18:40–20:40" in text
    assert "(автоматически)" not in text
    assert "Коммент: срочный" in text
    assert "Вместо: https://t.me/FaxriddinTuropov2" in text


def test_build_channel_detail_falls_back_to_draft_schedule_and_comment() -> None:
    start = datetime(2026, 7, 21, 8, 40, tzinfo=TASHKENT_TZ)
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        comment="общий коммент проекта",
        start_at=start,
        end_at=start + timedelta(hours=2),
        schedule_source=ScheduleSource.default_generated,
        posts=[
            BotPostDraft(
                local_id="p1",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@real",
                        channel_id=uuid4(),
                        display_name="Real",
                        url="https://t.me/real",
                        format=Format.telegram_1_24,
                    )
                ],
            )
        ],
    )
    text = build_channel_detail_text(draft.posts[0].channels[0], 1, draft, Language.ru)
    assert "Название: Real" in text
    assert "Ссылка: https://t.me/real" in text
    assert "Дата: 21.07.2026" in text
    assert "Время: 08:40–10:40 (автоматически)" in text
    assert "Коммент: общий коммент проекта" in text
    assert "Вместо:" not in text


def test_channel_comment_reset_cascade() -> None:
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        comment="общий РК",
        posts=[
            BotPostDraft(
                local_id="p1",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@ch",
                        channel_id=uuid4(),
                        comment="свой",
                    )
                ],
            )
        ],
    )
    ch = draft.posts[0].channels[0]
    assert channel_comment_for_display(ch, draft) == "свой"

    ch.comment = None
    assert channel_comment_for_display(ch, draft) == "общий РК"

    ch.comment = ""
    assert channel_comment_for_display(ch, draft) == "—"
    assert channel_comment_for_order(ch, draft) is None


def test_build_ask_project_tz_only_missing_fields() -> None:
    start = datetime.now(tz=TASHKENT_TZ) + timedelta(hours=2)
    with_name_no_time = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        project_name="Roodell",
        posts=[BotPostDraft(local_id="p1", channels=[BotChannelRef(status=ChannelRefStatus.found, query_raw="@ch")])],
    )
    text = build_ask_project_tz(with_name_no_time, Language.ru)
    assert text is not None
    assert "Проект: …" not in text
    assert "Проект уже: Roodell" in text
    assert "Время: …" in text
    assert draft_missing_project_tz_fields(with_name_no_time) is True

    ready = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        project_name="Roodell",
        start_at=start,
        end_at=start + timedelta(hours=2),
        posts=[BotPostDraft(local_id="p1", channels=[BotChannelRef(status=ChannelRefStatus.found, query_raw="@ch")])],
    )
    assert build_ask_project_tz(ready, Language.ru) is None
    assert draft_missing_project_tz_fields(ready) is False

    need_both = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[BotPostDraft(local_id="p1", channels=[BotChannelRef(status=ChannelRefStatus.found, query_raw="@ch")])],
    )
    both = build_ask_project_tz(need_both, Language.ru)
    assert both is not None
    assert "Проект: …" in both
    assert "Время: …" in both
    assert "Проект уже:" not in both


def test_build_orphan_prompt_text() -> None:
    assert build_orphan_prompt_text(Language.ru, need_channels=False, need_creative=False) is None
    only_ch = build_orphan_prompt_text(Language.ru, need_channels=True, need_creative=False)
    assert only_ch is not None
    assert "У поста нет канала" in only_ch
    assert "EMPTY" not in only_ch
    only_cr = build_orphan_prompt_text(Language.ru, need_channels=False, need_creative=True)
    assert only_cr is not None
    assert "креатива нет" in only_cr
    assert "EMPTY" in only_cr
    both = build_orphan_prompt_text(Language.ru, need_channels=True, need_creative=True)
    assert both is not None
    assert "У поста нет канала" in both
    assert "креатива нет" in both
    assert "\n\n" in both


def test_confirm_progress_bar_edges() -> None:
    assert confirm_progress_bar(0, 10) == "⬜️" * 10
    assert confirm_progress_bar(5, 10) == "🟩" * 5 + "⬜️" * 5
    assert confirm_progress_bar(10, 10) == "🟩" * 10
    assert confirm_progress_bar(1, 0) == "⬜️" * 10
    assert confirm_progress_bar(0, 0) == "⬜️" * 10
    assert confirm_progress_bar(50, 50) == "🟩" * 10


def test_confirm_progress_bar_scales_step_with_total() -> None:
    assert confirm_progress_bar(11, 50) == "🟩" * 2 + "⬜️" * 8
    assert confirm_progress_bar(27, 50) == "🟩" * 5 + "⬜️" * 5
    assert confirm_progress_bar(4, 50) == "⬜️" * 10
    assert confirm_progress_bar(5, 50) == "🟩" + "⬜️" * 9


def test_build_confirm_progress_text_includes_bar_and_total() -> None:
    text = build_confirm_progress_text(Language.ru, "cart", 2, 4)
    assert "🟩" in text
    assert "Добавляем в корзину: 4" in text
    assert "2/4" not in text
    orders = build_confirm_progress_text(Language.ru, "orders", 1, 3)
    assert "Генерация ордеров: 3" in orders
    posts = build_confirm_progress_text(Language.ru, "posts", 1, 2)
    assert "Привязываем посты: 2" in posts


def test_channel_mode_prompt_keeps_raw_urls() -> None:
    raw = "https://t.me/channel_a\nhttps://t.me/channel_b"
    text = build_channel_mode_prompt_text(Language.ru, raw)
    assert "https://t.me/channel_a" in text
    assert "https://t.me/channel_b" in text
    assert "@channel_a" not in text
    assert "К этим каналам не указан пост" in text
    ask = build_channel_mode_ask_creative_text(Language.ru, raw)
    assert "https://t.me/channel_a" in ask
    assert "https://t.me/channel_b" in ask
