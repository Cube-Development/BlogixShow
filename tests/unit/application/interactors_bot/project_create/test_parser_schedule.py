from datetime import datetime, timezone, timedelta

import pytest

from advertiser_blogger.application.interactors_bot.project_create.models import ScheduleSource
from advertiser_blogger.application.interactors_bot.project_create.parser import (
    looks_like_project_metadata,
    parse_project_reply,
)
from advertiser_blogger.application.interactors_bot.project_create.schedule import (
    PastScheduleError,
    TASHKENT_TZ,
    ceil_to_slot,
    resolve_project_schedule,
)

TZ = TASHKENT_TZ


def test_ceil_to_slot_examples():
    assert ceil_to_slot(datetime(2026, 7, 15, 17, 21, tzinfo=TZ)).hour == 17
    assert ceil_to_slot(datetime(2026, 7, 15, 17, 21, tzinfo=TZ)).minute == 25
    assert ceil_to_slot(datetime(2026, 7, 15, 17, 26, tzinfo=TZ)).minute == 30
    assert ceil_to_slot(datetime(2026, 7, 15, 17, 30, tzinfo=TZ)).minute == 30
    assert ceil_to_slot(datetime(2026, 7, 15, 17, 31, tzinfo=TZ)).minute == 35


def test_parse_ru_project_comment_time():
    parsed = parse_project_reply(
        "Проект: Test\nКомментарий: hello\nВремя: 17\n@channel_one\nhttps://t.me/channel_two"
    )
    assert parsed.project_name == "Test"
    assert parsed.comment == "hello"
    assert parsed.schedule.start_time == "17:00"
    assert "@channel_one" in parsed.channel_queries
    assert "@channel_two" in parsed.channel_queries


def test_parse_uz_mixed():
    parsed = parse_project_reply(
        "Loyiha: Test\nКомментарий: note\nVaqt: 17:00\n@uz_channel"
    )
    assert parsed.project_name == "Test"
    assert parsed.comment == "note"
    assert parsed.schedule.start_time == "17:00"
    assert parsed.channel_queries == ["@uz_channel"]


def test_parse_relative_and_range():
    parsed = parse_project_reply("Проект: Sale\nВремя: сегодня 17:00 - 19:00")
    assert parsed.schedule.relative_day == "today"
    assert parsed.schedule.start_time == "17:00"
    assert parsed.schedule.end_time == "19:00"

    parsed_uz = parse_project_reply("Loyiha: Sale\nVaqt: 17 dan 19 gacha")
    assert parsed_uz.schedule.start_time == "17:00"
    assert parsed_uz.schedule.end_time == "19:00"

    parsed_tmr = parse_project_reply("ertaga")
    assert parsed_tmr.schedule.relative_day == "tomorrow"


def test_parse_from_to_range():
    parsed = parse_project_reply("с 12:00 до 14:00")
    assert parsed.schedule.start_time == "12:00"
    assert parsed.schedule.end_time == "14:00"

    parsed_nach = parse_project_reply("начиная с 12:00 до 14:00")
    assert parsed_nach.schedule.start_time == "12:00"
    assert parsed_nach.schedule.end_time == "14:00"


def test_parse_space_separated_time_range():
    parsed = parse_project_reply("14 00 - 18 00")
    assert parsed.schedule.start_time == "14:00"
    assert parsed.schedule.end_time == "18:00"


def test_parse_today_v_hour():
    parsed = parse_project_reply("сегодня в 18")
    assert parsed.schedule.relative_day == "today"
    assert parsed.schedule.start_time == "18:00"

    parsed_tmr = parse_project_reply("завтра в 20")
    assert parsed_tmr.schedule.relative_day == "tomorrow"
    assert parsed_tmr.schedule.start_time == "20:00"


def test_parse_uz_bugun_soat():
    parsed = parse_project_reply("bugun soat 18")
    assert parsed.schedule.relative_day == "today"
    assert parsed.schedule.start_time == "18:00"

    parsed_tmr = parse_project_reply("ertaga soat 20")
    assert parsed_tmr.schedule.relative_day == "tomorrow"
    assert parsed_tmr.schedule.start_time == "20:00"


def test_parse_bare_hour_and_colon():
    assert parse_project_reply("18").schedule.start_time == "18:00"
    assert parse_project_reply("18:00").schedule.start_time == "18:00"
    assert parse_project_reply("14:00 - 18:00").schedule.end_time == "18:00"


def test_parse_pmpro_style_channels_project_from_to():
    parsed = parse_project_reply(
        "https://t.me/channel_one\n"
        "https://t.me/channel_two\n"
        "Проект: Roodell\n"
        "начиная с 12:00 до 14:00"
    )
    assert parsed.project_name == "Roodell"
    assert parsed.schedule.start_time == "12:00"
    assert parsed.schedule.end_time == "14:00"
    assert "@channel_one" in parsed.channel_queries
    assert "@channel_two" in parsed.channel_queries


def test_default_schedule_when_absent():
    now = datetime(2026, 7, 15, 17, 27, tzinfo=TZ)
    schedule = resolve_project_schedule(None, now=now)
    assert schedule.start_at == datetime(2026, 7, 15, 17, 30, tzinfo=TZ)
    assert schedule.end_at == datetime(2026, 7, 15, 19, 30, tzinfo=TZ)
    assert schedule.source == ScheduleSource.default_generated


def test_user_defined_start_only():
    now = datetime(2026, 7, 15, 10, 0, tzinfo=TZ)
    parsed = parse_project_reply("Время: 17")
    schedule = resolve_project_schedule(parsed.schedule, now=now)
    assert schedule.start_at == datetime(2026, 7, 15, 17, 0, tzinfo=TZ)
    assert schedule.end_at == datetime(2026, 7, 15, 19, 0, tzinfo=TZ)
    assert schedule.source == ScheduleSource.user_defined


def test_past_schedule_rejected():
    now = datetime(2026, 7, 15, 18, 0, tzinfo=TZ)
    parsed = parse_project_reply("Время: 15:00")
    with pytest.raises(PastScheduleError):
        resolve_project_schedule(parsed.schedule, now=now)


def test_bot_form_past_schedule_snaps_to_slot():
    from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import (
        resolve_bot_form_schedule,
    )

    now = datetime(2026, 7, 15, 18, 7, tzinfo=TZ)
    parsed = parse_project_reply("Время: 15:00")
    schedule = resolve_bot_form_schedule(
        parsed.schedule,
        timezone="Asia/Tashkent",
        default_duration_hours=3,
        now=now,
    )
    assert schedule.start_at == datetime(2026, 7, 15, 18, 10, tzinfo=TZ)
    assert schedule.end_at == datetime(2026, 7, 15, 21, 10, tzinfo=TZ)
    assert schedule.source == ScheduleSource.default_generated


def test_bot_form_past_date_snaps_to_slot():
    from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import (
        resolve_bot_form_schedule,
    )
    from advertiser_blogger.application.interactors_bot.project_create.models import (
        ParsedScheduleFragments,
    )

    now = datetime(2026, 7, 15, 18, 7, tzinfo=TZ)
    schedule = resolve_bot_form_schedule(
        ParsedScheduleFragments(date="10.07.2026", start_time="12:00"),
        timezone="Asia/Tashkent",
        default_duration_hours=3,
        now=now,
    )
    assert schedule.start_at == datetime(2026, 7, 15, 18, 10, tzinfo=TZ)
    assert schedule.end_at == datetime(2026, 7, 15, 21, 10, tzinfo=TZ)
    assert schedule.source == ScheduleSource.default_generated


def test_normalize_time_dot_separator():
    from advertiser_blogger.application.interactors_bot.project_create.schedule_fragments import (
        normalize_time_token,
    )

    assert normalize_time_token("14.00") == "14:00"
    assert normalize_time_token("14 00") == "14:00"
    assert normalize_time_token("14") == "14:00"



def test_date_only_tomorrow_uses_ceil_now_time():
    now = datetime(2026, 7, 15, 17, 27, tzinfo=TZ)
    parsed = parse_project_reply("завтра")
    schedule = resolve_project_schedule(parsed.schedule, now=now)
    assert schedule.start_at.date().isoformat() == "2026-07-16"
    assert schedule.start_at.hour == 17
    assert schedule.start_at.minute == 30
    assert schedule.end_at.hour == 19
    assert schedule.end_at.minute == 30


def test_looks_like_project_metadata():
    assert looks_like_project_metadata(
        "Проект: Test\nКомментарий: hello\nВремя: 17\n@channel_one"
    )
    assert looks_like_project_metadata("@only_channel")
    assert looks_like_project_metadata("Время: завтра 17:00")
    assert looks_like_project_metadata("сегодня 17:00 - 19:00")
    assert looks_like_project_metadata("bugun 17:00")
    assert looks_like_project_metadata("https://t.me/+EdifkdTPC8s2Y2Fi")
    assert looks_like_project_metadata("https://t.me/joinchat/AAAAAEkdTPC8s2Y2Fi")
    assert not looks_like_project_metadata("просто рекламный текст без полей")
    assert not looks_like_project_metadata("")
    assert not looks_like_project_metadata("   ")


def test_parse_invite_link_as_channel_query():
    parsed = parse_project_reply("https://t.me/+EdifkdTPC8s2Y2Fi")
    assert parsed.channel_queries == ["https://t.me/+EdifkdTPC8s2Y2Fi"]

    parsed_join = parse_project_reply("https://t.me/joinchat/AAAAAEkdTPC8s2Y2Fi")
    assert parsed_join.channel_queries == ["https://t.me/joinchat/AAAAAEkdTPC8s2Y2Fi"]


def test_ad_caption_with_bugun_is_not_metadata():
    """PMPro-style creative caption must not match relative-day 'bugun' or phone as time."""
    caption = (
        "🎓 Central Asian University Oʻzbekistondagi eng yirik bitiruv marosimlaridan birini oʻtkazdi\n\n"
        "Bugun bitiruvchilarni yangi imkoniyatlar, yuksak marralar va katta muvaffaqiyatlar kutmoqda.\n\n"
        "👉 Qabul davom etmoqda!\n\n"
        "📞 71-208-12-34"
    )
    assert not looks_like_project_metadata(caption)
    parsed = parse_project_reply(caption)
    assert parsed.schedule.relative_day is None
    assert parsed.schedule.start_time is None
    assert parsed.schedule.end_time is None


def test_phone_number_is_not_time_range():
    assert not looks_like_project_metadata("📞 71-208-12-34")
    assert looks_like_project_metadata("12:00 - 14:00")
    assert looks_like_project_metadata("12 - 14")
