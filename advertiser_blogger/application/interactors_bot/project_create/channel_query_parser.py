"""Parse channel line with optional comment / date / time (RU + UZ)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from advertiser_blogger.application.interactors_bot.project_create.models import (
    ParsedScheduleFragments,
)
from advertiser_blogger.application.interactors_bot.project_create.schedule_fragments import (
    apply_date_value,
    apply_time_value,
    consume_leading_schedule,
    extract_schedule_from_text,
    split_channel_prefix,
    strip_schedule_tokens_from_comment,
)

_CHANNEL_META_ALIASES: list[tuple[str, str]] = sorted(
    [
        ("комментарий", "comment"),
        ("коммент", "comment"),
        ("примечание", "comment"),
        ("описание", "comment"),
        ("izoh", "comment"),
        ("kommentariya", "comment"),
        ("tavsif", "comment"),
        ("comment", "comment"),
        ("дата", "date"),
        ("sana", "date"),
        ("date", "date"),
        ("время", "time"),
        ("vaqt", "time"),
        ("time", "time"),
    ],
    key=lambda x: len(x[0]),
    reverse=True,
)

_COMMENT_ALIASES = frozenset(
    alias for alias, key in _CHANNEL_META_ALIASES if key == "comment"
)

_SEP_RE = re.compile(r"^[\s:–—\-]+")


@dataclass
class ParsedChannelQueryLine:
    channel_query: str
    comment: str | None = None
    schedule: ParsedScheduleFragments = field(default_factory=ParsedScheduleFragments)


def line_has_channel_meta(text: str) -> bool:
    if not text or not text.strip():
        return False
    return _find_meta_split(text) is not None


def line_has_channel_trailing_schedule(text: str) -> bool:
    """True if line is channel + any trailing text (keep full line for resolve)."""
    split = split_channel_prefix(text)
    if split is None:
        return False
    _, rest = split
    return bool(rest and rest.strip())


def parse_channel_query_line(text: str) -> ParsedChannelQueryLine:
    """
    Split channel line into query + optional comment/schedule.

    Schedule is parsed before comment so comments never swallow times::

        https://t.me/x 11:00 срочный
        https://t.me/x 11:00 комментарий: срочный
        https://t.me/x комментарий: завтра 12:00 срочный
        https://t.me/x | дата: завтра 14:00 | комментарий: срочно
    """
    raw = (text or "").strip()
    if not raw:
        return ParsedChannelQueryLine(channel_query="")

    if "|" in raw:
        pipe_parsed = _parse_pipe_channel_line(raw)
        if pipe_parsed is not None:
            return pipe_parsed

    prefix = split_channel_prefix(raw)
    if prefix is not None:
        channel, rest = prefix
        return _parse_channel_with_rest(channel=channel, rest=rest)

    split = _find_meta_split(raw)
    if split is None:
        return ParsedChannelQueryLine(channel_query=raw)

    channel_part, field_key, value = split
    channel_query = channel_part.strip() or raw

    # Time before comment keyword: ``https://t.me/x 11:00 комментарий: …``
    # (no space-only channel prefix match if somehow missed — also peel from channel_part)
    nested = split_channel_prefix(channel_query + (" " + value if field_key else ""))
    if nested is None and channel_part.strip():
        maybe = split_channel_prefix(channel_part.strip() + " x")
        # channel_part may be ``https://t.me/x 11:00``
        nested_part = split_channel_prefix(channel_part.strip() + " _")
        # Better: if channel_part has trailing schedule
        from_part = split_channel_prefix(channel_part.strip()) if " " in channel_part.strip() else None
        if " " in channel_part.strip():
            # re-match with synthetic: channel_part is "url 11:00" — use regex on channel_part + " ."
            m = re.match(
                r"^((?:https?://)?(?:t|telegram)\.me/[A-Za-z0-9_]{4,}|@[A-Za-z0-9_]{4,})\s+(.+)$",
                channel_part.strip(),
                re.IGNORECASE,
            )
            if m is not None:
                channel_query = m.group(1)
                leading_rest = m.group(2).strip()
                result = _parse_channel_with_rest(
                    channel=channel_query,
                    rest=f"{leading_rest} {_field_keyword_label(field_key)} {value}".strip()
                    if field_key == "comment"
                    else (
                        f"{leading_rest} {_field_keyword_label(field_key)}: {value}".strip()
                        if field_key
                        else leading_rest
                    ),
                )
                if field_key == "time" and not (
                    result.schedule.start_time or result.schedule.end_time
                ):
                    apply_time_value(result.schedule, value)
                elif field_key == "date":
                    apply_date_value(result.schedule, value)
                return result

    result = ParsedChannelQueryLine(
        channel_query=channel_query,
        schedule=ParsedScheduleFragments(),
    )
    value = value.strip()

    if field_key == "comment":
        _apply_comment_value(result, value)
    elif field_key == "date":
        apply_date_value(result.schedule, value)
        extract_schedule_from_text(value, result.schedule)
    elif field_key == "time":
        apply_time_value(result.schedule, value)

    return result


_PIPE_SEGMENT_RE = re.compile(
    r"^\s*(?P<alias>комментарий|коммент|примечание|описание|izoh|kommentariya|tavsif|comment|"
    r"дата|sana|date|время|vaqt|time)\s*[:\-–—]\s*(?P<value>.+)\s*$",
    re.IGNORECASE,
)


def _parse_pipe_channel_line(text: str) -> ParsedChannelQueryLine | None:
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 2 or not parts[0]:
        return None
    result = ParsedChannelQueryLine(
        channel_query=parts[0],
        schedule=ParsedScheduleFragments(),
    )
    saw_meta = False
    for segment in parts[1:]:
        if not segment:
            continue
        match = _PIPE_SEGMENT_RE.match(segment)
        if match is None:
            # Free trailing segment without key — treat as comment if empty so far.
            if result.comment is None and segment:
                result.comment = segment
                saw_meta = True
            continue
        alias = match.group("alias").lower().replace("ё", "е")
        value = match.group("value").strip()
        field_key = next(
            (key for a, key in _CHANNEL_META_ALIASES if a == alias),
            None,
        )
        if field_key is None:
            for a, key in _CHANNEL_META_ALIASES:
                if a.lower().replace("ё", "е") == alias:
                    field_key = key
                    break
        if field_key == "comment":
            _apply_comment_value(result, value)
            saw_meta = True
        elif field_key == "date":
            apply_date_value(result.schedule, value)
            extract_schedule_from_text(value, result.schedule)
            saw_meta = True
        elif field_key == "time":
            apply_time_value(result.schedule, value)
            saw_meta = True
    return result if saw_meta or len(parts) >= 2 else None


def _field_keyword_label(field_key: str) -> str:
    if field_key == "comment":
        return "комментарий"
    if field_key == "time":
        return "время"
    if field_key == "date":
        return "дата"
    return field_key


def _parse_channel_with_rest(*, channel: str, rest: str) -> ParsedChannelQueryLine:
    result = ParsedChannelQueryLine(
        channel_query=channel.strip(),
        schedule=ParsedScheduleFragments(),
    )
    work = rest.strip()
    if not work:
        return result

    schedule, remainder = consume_leading_schedule(work)
    result.schedule = schedule

    remainder = remainder.strip()
    comment_split = _find_meta_split(remainder) if remainder else None
    if comment_split is None and not (
        schedule.date or schedule.start_time or schedule.end_time or schedule.relative_day
    ):
        # Whole rest may start with meta keyword (no leading time).
        comment_split = _find_meta_split(work)
        if comment_split is not None:
            _, field_key, value = comment_split
            if field_key == "comment":
                _apply_comment_value(result, value.strip())
            elif field_key == "date":
                apply_date_value(result.schedule, value.strip())
                extract_schedule_from_text(value.strip(), result.schedule)
            elif field_key == "time":
                apply_time_value(result.schedule, value.strip())
            return result

    if comment_split is not None:
        before, field_key, value = comment_split
        # Schedule may also sit in ``before`` (already consumed) or in value.
        if field_key == "comment":
            _apply_comment_value(result, value.strip())
        elif field_key == "date":
            apply_date_value(result.schedule, value.strip())
            extract_schedule_from_text(value.strip(), result.schedule)
        elif field_key == "time":
            apply_time_value(result.schedule, value.strip())
        elif before.strip() and not result.comment:
            result.comment = before.strip() or None
        return result

    if remainder:
        result.comment = remainder
    return result


def _apply_comment_value(result: ParsedChannelQueryLine, value: str) -> None:
    if not value:
        return
    leading, rem = consume_leading_schedule(value)
    _merge_schedule(result.schedule, leading)
    extract_schedule_from_text(value, result.schedule)
    stripped = strip_schedule_tokens_from_comment(value, result.schedule)
    if stripped:
        result.comment = stripped
    elif rem:
        result.comment = rem
    else:
        # Keep prose that is not pure schedule; if only schedule — no comment.
        result.comment = None


def _merge_schedule(target: ParsedScheduleFragments, source: ParsedScheduleFragments) -> None:
    if source.relative_day and not target.relative_day:
        target.relative_day = source.relative_day
    if source.date and not target.date:
        target.date = source.date
    if source.start_time and not target.start_time:
        target.start_time = source.start_time
    if source.end_time and not target.end_time:
        target.end_time = source.end_time


def _find_meta_split(text: str) -> tuple[str, str, str] | None:
    lowered = text.lower().replace("ё", "е")
    best: tuple[int, int, str] | None = None
    for alias, field_key in _CHANNEL_META_ALIASES:
        alias_l = alias.lower().replace("ё", "е")
        start = 0
        while True:
            idx = lowered.find(alias_l, start)
            if idx < 0:
                break
            before_ok = idx == 0 or lowered[idx - 1].isspace()
            end = idx + len(alias_l)
            after_ok = end >= len(lowered) or lowered[end] in " :–—-\t"
            if before_ok and after_ok:
                if best is None or idx < best[0] or (idx == best[0] and len(alias_l) > best[1]):
                    best = (idx, len(alias_l), field_key)
                break
            start = idx + 1
    if best is None:
        return None
    idx, alias_len, field_key = best
    channel_part = text[:idx]
    value = _SEP_RE.sub("", text[idx + alias_len :])
    return channel_part, field_key, value
