from advertiser_blogger.application.interactors_bot.project_create.channel_query_parser import (
    line_has_channel_meta,
    parse_channel_query_line,
)
from advertiser_blogger.application.interactors_bot.project_create.parser import (
    looks_like_project_metadata,
    parse_project_reply,
)


def test_parse_url_with_comment_and_tomorrow():
    parsed = parse_channel_query_line(
        "https://t.me/ru2ch комментарий - любое время завтра"
    )
    assert parsed.channel_query == "https://t.me/ru2ch"
    assert parsed.comment == "любое время"
    assert parsed.schedule.relative_day == "tomorrow"


def test_parse_freeform_with_comment():
    parsed = parse_channel_query_line(
        "канал самарканда води комментарий - любое время завтра"
    )
    assert "самарканда" in parsed.channel_query.lower() or parsed.channel_query.startswith("канал")
    assert parsed.comment is not None
    assert "любое" in (parsed.comment or "")
    assert parsed.schedule.relative_day == "tomorrow"


def test_parse_uz_izoh_vaqt():
    parsed = parse_channel_query_line("@foo izoh - ertaga 17:00")
    assert parsed.channel_query == "@foo"
    assert parsed.comment is None
    assert parsed.schedule.relative_day == "tomorrow"
    assert parsed.schedule.start_time == "17:00"


def test_parse_time_keyword():
    parsed = parse_channel_query_line("@foo время: завтра 12:00 - 14:00")
    assert parsed.channel_query == "@foo"
    assert parsed.schedule.relative_day == "tomorrow"
    assert parsed.schedule.start_time == "12:00"
    assert parsed.schedule.end_time == "14:00"


def test_line_has_channel_meta():
    assert line_has_channel_meta("https://t.me/x комментарий - hello")
    assert line_has_channel_meta("@x vaqt 17")
    assert not line_has_channel_meta("https://t.me/x")


def test_project_reply_keeps_full_channel_meta_line():
    text = "https://t.me/ru2ch комментарий - любое время завтра"
    assert looks_like_project_metadata(text)
    parsed = parse_project_reply(text)
    assert any("ru2ch" in q for q in parsed.channel_queries)
    assert any("комментарий" in q for q in parsed.channel_queries)


def test_parse_url_with_trailing_time_no_keyword():
    parsed = parse_channel_query_line("https://t.me/Jonli_Bolta 11:00")
    assert parsed.channel_query == "https://t.me/Jonli_Bolta"
    assert parsed.schedule.start_time == "11:00"
    assert parsed.comment is None


def test_parse_at_with_trailing_time():
    parsed = parse_channel_query_line("@bankuz_official 12:00")
    assert parsed.channel_query == "@bankuz_official"
    assert parsed.schedule.start_time == "12:00"


def test_line_has_trailing_schedule():
    from advertiser_blogger.application.interactors_bot.project_create.channel_query_parser import (
        line_has_channel_trailing_schedule,
    )

    assert line_has_channel_trailing_schedule("https://t.me/Jonli_Bolta 11:00")
    assert not line_has_channel_trailing_schedule("https://t.me/Jonli_Bolta")
    # Free comment without time — keep full line for resolve.
    assert line_has_channel_trailing_schedule(
        "https://t.me/Jonli_Bolta hello world prose"
    )
    assert line_has_channel_trailing_schedule("https://t.me/Jonli_Bolta срочный")


def test_project_reply_keeps_channel_lines_with_times():
    text = (
        "https://t.me/Jonli_Bolta 11:00\n"
        "https://t.me/Yangiliklari24uz 11:20\n"
        "https://t.me/Bankir 13:00"
    )
    assert looks_like_project_metadata(text)
    parsed = parse_project_reply(text)
    assert len(parsed.channel_queries) == 3
    assert all(" " in q for q in parsed.channel_queries)

    from advertiser_blogger.application.interactors_bot.project_create.channel_query_parser import (
        parse_channel_query_line,
    )

    first = parse_channel_query_line(parsed.channel_queries[0])
    assert first.channel_query == "https://t.me/Jonli_Bolta"
    assert first.schedule.start_time == "11:00"
    second = parse_channel_query_line(parsed.channel_queries[1])
    assert second.schedule.start_time == "11:20"


def test_trailing_time_with_free_comment():
    parsed = parse_channel_query_line("https://t.me/Jonli_Bolta 11:00 срочный пост")
    assert parsed.channel_query == "https://t.me/Jonli_Bolta"
    assert parsed.schedule.start_time == "11:00"
    assert parsed.comment == "срочный пост"


def test_trailing_time_with_comment_keyword():
    parsed = parse_channel_query_line(
        "https://t.me/Jonli_Bolta 11:00 комментарий: срочный"
    )
    assert parsed.schedule.start_time == "11:00"
    assert parsed.comment == "срочный"


def test_comment_keyword_with_schedule_and_prose():
    parsed = parse_channel_query_line(
        "https://t.me/Jonli_Bolta комментарий: завтра 12:00 срочный"
    )
    assert parsed.channel_query == "https://t.me/Jonli_Bolta"
    assert parsed.schedule.relative_day == "tomorrow"
    assert parsed.schedule.start_time == "12:00"
    assert parsed.comment == "срочный"


def test_comment_does_not_eat_time_before_keyword():
    parsed = parse_channel_query_line(
        "https://t.me/Jonli_Bolta 14:00 комментарий: hello"
    )
    assert parsed.schedule.start_time == "14:00"
    assert parsed.comment == "hello"


def test_line_has_trailing_with_time_and_comment():
    from advertiser_blogger.application.interactors_bot.project_create.channel_query_parser import (
        line_has_channel_trailing_schedule,
    )

    assert line_has_channel_trailing_schedule(
        "https://t.me/Jonli_Bolta 11:00 срочный"
    )
    assert line_has_channel_trailing_schedule(
        "https://t.me/Jonli_Bolta комментарий: hello"
    )


def test_free_comment_without_time_stays_in_channel_queries():
    text = "https://t.me/Jonli_Bolta срочный"
    assert looks_like_project_metadata(text)
    parsed = parse_project_reply(text)
    assert parsed.channel_queries == ["https://t.me/Jonli_Bolta срочный"]

    line = parse_channel_query_line(parsed.channel_queries[0])
    assert line.channel_query == "https://t.me/Jonli_Bolta"
    assert line.comment == "срочный"
    assert line.schedule.start_time is None


def test_parse_pipe_canon_template():
    parsed = parse_channel_query_line(
        "https://t.me/ru2ch | дата: завтра 14:00 | комментарий: срочно"
    )
    assert parsed.channel_query == "https://t.me/ru2ch"
    assert parsed.comment == "срочно"
    assert parsed.schedule.relative_day == "tomorrow"
    assert parsed.schedule.start_time == "14:00"


def test_parse_pipe_date_only_dotted():
    parsed = parse_channel_query_line("https://t.me/ru2ch | дата: 08.08.2026")
    assert parsed.channel_query == "https://t.me/ru2ch"
    assert parsed.schedule.date == "08.08.2026"


def test_parse_pipe_time_formats():
    for raw in ("14:00", "14 00", "14.00", "14"):
        parsed = parse_channel_query_line(f"https://t.me/ru2ch | время: {raw}")
        assert parsed.schedule.start_time == "14:00", raw
