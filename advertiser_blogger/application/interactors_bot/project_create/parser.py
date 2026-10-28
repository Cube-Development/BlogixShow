from __future__ import annotations

import re

from advertiser_blogger.application.interactors_bot.project_create.aliases import (
    ALIAS_LOOKUP,
)
from advertiser_blogger.application.interactors_bot.project_create.channel_query_parser import (
    line_has_channel_meta,
    line_has_channel_trailing_schedule,
)
from advertiser_blogger.application.interactors_bot.project_create.models import (
    ParsedProjectReply,
)
from advertiser_blogger.application.interactors_bot.project_create.normalizer import (
    normalize_label,
    normalize_text,
)
from advertiser_blogger.application.interactors_bot.project_create.schedule_fragments import (
    apply_start_value,
    normalize_time_token,
    try_parse_inline_schedule,
)

_CHANNEL_URL_RE = re.compile(
    r"(?:https?://)?(?:t|telegram)\.me/\+([A-Za-z0-9_-]{8,})"
    r"|(?:https?://)?(?:t|telegram)\.me/joinchat/([A-Za-z0-9_-]{8,})"
    r"|(?:https?://)?(?:t|telegram)\.me/([A-Za-z0-9_]{4,})"
    r"|@([A-Za-z0-9_]{4,})",
    re.IGNORECASE,
)


def parse_project_reply(text: str) -> ParsedProjectReply:
    result = ParsedProjectReply()
    if not text or not text.strip():
        return result

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    collecting_channels = False

    for line in lines:
        if collecting_channels:
            if _should_keep_full_channel_line(line):
                result.channel_queries.append(line.strip())
            else:
                queries = _extract_channel_queries(line)
                if queries:
                    result.channel_queries.extend(queries)
                elif _looks_like_channel_line(line):
                    result.channel_queries.append(line.strip())
                else:
                    # stop channel block if labeled field appears
                    field_key, value = _split_labeled_line(line)
                    if field_key is not None:
                        collecting_channels = False
                        _apply_field(result, field_key, value)
                    else:
                        result.unmatched_lines.append(line)
            continue

        field_key, value = _split_labeled_line(line)
        if field_key == "channels":
            collecting_channels = True
            if value:
                if _should_keep_full_channel_line(value):
                    result.channel_queries.append(value.strip())
                else:
                    result.channel_queries.extend(_extract_channel_queries(value) or [value])
            continue
        if field_key is not None:
            _apply_field(result, field_key, value)
            continue

        # Unlabeled: try channel URLs/@, or bare time range
        channel_queries = _extract_channel_queries(line)
        if channel_queries and _should_keep_full_channel_line(line):
            result.channel_queries.append(line.strip())
            continue
        if channel_queries and _line_is_mostly_channels(line, channel_queries):
            result.channel_queries.extend(channel_queries)
            continue
        # Freeform swap request with meta keywords (no @/url)
        if line_has_channel_meta(line) and not _split_labeled_line(line)[0]:
            result.channel_queries.append(line.strip())
            continue

        if try_parse_inline_schedule(line, result.schedule):
            continue

        result.unmatched_lines.append(line)

    # Also scan whole text for channels not caught as lines
    if not result.channel_queries:
        result.channel_queries = _extract_channel_queries(text)

    return result


def looks_like_project_metadata(text: str) -> bool:
    parsed = parse_project_reply(text)
    if parsed.channel_queries:
        return True
    if parsed.project_name or parsed.comment:
        return True
    schedule = parsed.schedule
    return bool(schedule.date or schedule.start_time or schedule.end_time or schedule.relative_day)


def _should_keep_full_channel_line(line: str) -> bool:
    return line_has_channel_meta(line) or line_has_channel_trailing_schedule(line)


def _split_labeled_line(line: str) -> tuple[str | None, str]:
    normalized = normalize_text(line)
    for alias, field_key in ALIAS_LOOKUP:
        # "alias: value" or "alias value"
        if normalized.startswith(alias):
            rest = normalized[len(alias) :].lstrip()
            if rest.startswith(":"):
                rest = rest[1:].strip()
            elif rest == "" or rest[0].isalnum() or rest[0] in "@http":
                # require "с:" / "до:" for short aliases — not "с 12:00 до 14:00"
                if len(alias) <= 2 and not (
                    ":" in line[: len(alias) + 2] or rest.startswith(("http", "@"))
                ):
                    continue
            # Rebuild value from original line after first ":" if present
            if ":" in line:
                value = line.split(":", 1)[1].strip()
            else:
                # strip alias from start case-insensitively
                value = _strip_prefix_ci(line, alias).strip()
            return field_key, value
    return None, ""


def _strip_prefix_ci(text: str, prefix: str) -> str:
    if normalize_text(text).startswith(prefix):
        # find end of prefix in original by length of normalized prefix chars
        idx = 0
        matched = 0
        norm_prefix = normalize_label(prefix)
        lowered = text.lower().replace("ё", "е")
        while idx < len(lowered) and matched < len(norm_prefix):
            ch = lowered[idx]
            idx += 1
            if ch.isspace():
                continue
            matched += 1
        return text[idx:]
    return text


def _apply_field(result: ParsedProjectReply, field_key: str, value: str) -> None:
    if field_key == "project":
        result.project_name = value.strip() or result.project_name
    elif field_key == "comment":
        result.comment = value.strip() or result.comment
    elif field_key == "start_time":
        apply_start_value(result.schedule, value)
    elif field_key == "end_time":
        result.schedule.end_time = normalize_time_token(value) or result.schedule.end_time
    elif field_key == "channels":
        result.channel_queries.extend(_extract_channel_queries(value) or ([value] if value else []))


def _extract_channel_queries(text: str) -> list[str]:
    found: list[str] = []
    for match in _CHANNEL_URL_RE.finditer(text):
        plus_hash = match.group(1)
        joinchat_hash = match.group(2)
        username = match.group(3) or match.group(4)
        if plus_hash:
            found.append(f"https://t.me/+{plus_hash}")
        elif joinchat_hash:
            found.append(f"https://t.me/joinchat/{joinchat_hash}")
        elif username:
            found.append(f"@{username.lstrip('@')}")
    return found


def _looks_like_channel_line(line: str) -> bool:
    lowered = normalize_text(line)
    return lowered.startswith("@") or "t.me/" in lowered or "telegram.me/" in lowered


def _line_is_mostly_channels(line: str, queries: list[str]) -> bool:
    stripped = _CHANNEL_URL_RE.sub(" ", line)
    leftover = re.sub(r"[\s,;]+", "", stripped)
    return len(leftover) < 3 and len(queries) > 0
