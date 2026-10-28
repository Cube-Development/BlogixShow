"""Shared schedule-fragment parsing for project create (RU + UZ)."""

from __future__ import annotations

import re

from advertiser_blogger.application.interactors_bot.project_create.aliases import (
    RELATIVE_DAY_LOOKUP,
)
from advertiser_blogger.application.interactors_bot.project_create.models import (
    ParsedScheduleFragments,
)
from advertiser_blogger.application.interactors_bot.project_create.normalizer import (
    normalize_text,
)

# HH:MM or HH.MM or HH MM or HH
_TIME_ATOM = r"\d{1,2}(?::\d{2}|\.\d{2}|\s+\d{2})?"

_TIME_RANGE_RE = re.compile(
    rf"(?<![\d./-])(?P<start>{_TIME_ATOM})\s*[-–—]\s*(?P<end>{_TIME_ATOM})(?![\d./-])",
)
_FROM_TO_RANGE_RE = re.compile(
    rf"(?:начиная\s+)?с\s+(?P<start>{_TIME_ATOM})\s+до\s+(?P<end>{_TIME_ATOM})",
)
_UZ_RANGE_RE = re.compile(
    rf"(?P<start>{_TIME_ATOM})\s+dan\s+(?P<end>{_TIME_ATOM})\s*(?:gacha)?",
    re.IGNORECASE,
)
_ABS_DATE_RE = re.compile(r"\b(\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)\b")
_TIME_TOKEN_RE = re.compile(rf"\b({_TIME_ATOM})\b")
_TIME_PARTICLE_RE = re.compile(
    r"^(?:в|soat|da)\s+",
    re.IGNORECASE,
)
_CHANNEL_WITH_TRAILING_RE = re.compile(
    r"^("
    r"(?:https?://)?(?:t|telegram)\.me/\+[A-Za-z0-9_-]{8,}"
    r"|(?:https?://)?(?:t|telegram)\.me/joinchat/[A-Za-z0-9_-]{8,}"
    r"|(?:https?://)?(?:t|telegram)\.me/[A-Za-z0-9_]{4,}"
    r"|@[A-Za-z0-9_]{4,}"
    r")\s+(.+)$",
    re.IGNORECASE,
)


def normalize_time_token(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if ":" in raw or "." in raw:
        sep = ":" if ":" in raw else "."
        parts = raw.split(sep)
        if len(parts) != 2:
            return None
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
        return None
    space_parts = raw.split()
    if len(space_parts) == 2:
        try:
            h, m = int(space_parts[0]), int(space_parts[1])
        except ValueError:
            return None
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
        return None
    try:
        h = int(raw)
    except ValueError:
        return None
    if 0 <= h <= 23:
        return f"{h:02d}:00"
    return None


def find_time_range(text: str) -> re.Match[str] | None:
    for pattern in (_TIME_RANGE_RE, _FROM_TO_RANGE_RE, _UZ_RANGE_RE):
        for match in pattern.finditer(text):
            start = normalize_time_token(match.group("start"))
            end = normalize_time_token(match.group("end"))
            if start is not None and end is not None:
                return match
    return None


def apply_time_range(schedule: ParsedScheduleFragments, range_match: re.Match[str]) -> bool:
    start = normalize_time_token(range_match.group("start"))
    end = normalize_time_token(range_match.group("end"))
    if start is None or end is None:
        return False
    schedule.start_time = start
    schedule.end_time = end
    return True


def _strip_time_particles(rest: str) -> str:
    rest = rest.strip()
    while True:
        stripped = _TIME_PARTICLE_RE.sub("", rest, count=1)
        if stripped == rest:
            return rest
        rest = stripped.strip()


def schedule_rest_after_relative_day(rest: str) -> bool:
    """True if rest after сегодня/bugun is a time fragment, not ad prose."""
    rest = _strip_time_particles(rest.strip())
    if not rest:
        return True
    if find_time_range(rest) is not None:
        return True
    if _TIME_TOKEN_RE.fullmatch(rest) and normalize_time_token(rest) is not None:
        return True
    return False


def looks_like_schedule_fragment(text: str) -> bool:
    if not text or not text.strip():
        return False
    schedule = ParsedScheduleFragments()
    if not try_parse_inline_schedule(text, schedule):
        return False
    return bool(
        schedule.date
        or schedule.start_time
        or schedule.end_time
        or schedule.relative_day
    )


def _leading_time_span(text: str) -> tuple[str, str, str | None] | None:
    """If text starts with a time or range, return (matched, start_hhmm, end_hhmm|None)."""
    text = text.strip()
    if not text:
        return None
    for pattern in (_FROM_TO_RANGE_RE, _UZ_RANGE_RE, _TIME_RANGE_RE):
        match = pattern.search(text)
        if match is not None and match.start() == 0:
            start = normalize_time_token(match.group("start"))
            end = normalize_time_token(match.group("end"))
            if start is not None and end is not None:
                return match.group(0), start, end
    match = re.match(rf"^({_TIME_ATOM})\b", text)
    if match is not None:
        normalized = normalize_time_token(match.group(1))
        if normalized is not None:
            return match.group(0), normalized, None
    return None


def consume_leading_schedule(text: str) -> tuple[ParsedScheduleFragments, str]:
    """
    Consume a leading schedule fragment from ``text``.

    Supports ``11:00 …``, ``сегодня в 18 …``, ``14:00 - 16:00 …``.
    Returns (schedule, remainder_after_schedule).
    """
    schedule = ParsedScheduleFragments()
    work = normalize_text(text or "")
    if not work:
        return schedule, ""

    for alias, day_key in RELATIVE_DAY_LOOKUP:
        if work == alias:
            schedule.relative_day = day_key
            return schedule, ""
        prefix = alias + " "
        if work.startswith(prefix):
            after_day = work[len(prefix) :].strip()
            after_particles = _strip_time_particles(after_day)
            if after_particles == "" or _leading_time_span(after_particles) is not None:
                schedule.relative_day = day_key
                work = after_particles
                break

    span = _leading_time_span(work)
    if span is not None:
        matched, start, end = span
        schedule.start_time = start
        if end is not None:
            schedule.end_time = end
        work = work[len(matched) :].strip()
        work = re.sub(r"^[\s:–—\-]+", "", work).strip()
        return schedule, work

    if schedule.relative_day:
        return schedule, work

    return schedule, work


def split_channel_prefix(text: str) -> tuple[str, str] | None:
    """Split ``https://t.me/x …`` / ``@name …`` into (channel, rest)."""
    raw = (text or "").strip()
    match = _CHANNEL_WITH_TRAILING_RE.match(raw)
    if match is None:
        return None
    return match.group(1), match.group(2).strip()


def try_split_channel_trailing_schedule(text: str) -> tuple[str, str] | None:
    """Split ``https://t.me/x 11:00`` into (channel, schedule_text)."""
    split = split_channel_prefix(text)
    if split is None:
        return None
    channel, rest = split
    schedule, remainder = consume_leading_schedule(rest)
    has_schedule = bool(
        schedule.date or schedule.start_time or schedule.end_time or schedule.relative_day
    )
    if not has_schedule:
        return None
    # Keep original rest so callers can still parse comment after time.
    return channel, rest


def strip_schedule_tokens_from_comment(
        text: str,
        schedule: ParsedScheduleFragments,
) -> str | None:
    """Remove relative-day aliases and matched time tokens; keep other prose."""
    if not text or not text.strip():
        return None
    work = normalize_text(text)
    if schedule.relative_day:
        for alias, day_key in RELATIVE_DAY_LOOKUP:
            if day_key != schedule.relative_day:
                continue
            work = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", " ", work)
    if schedule.start_time or schedule.end_time:
        range_match = find_time_range(work)
        if range_match is not None:
            work = work[: range_match.start()] + " " + work[range_match.end() :]
        if schedule.start_time:
            for token in (schedule.start_time, schedule.start_time.lstrip("0") or "0"):
                # also bare hour "18" for "18:00"
                pass
            hour = str(int(schedule.start_time.split(":")[0]))
            minute = schedule.start_time.split(":")[1]
            variants = {schedule.start_time, f"{hour}:{minute}", hour}
            if minute == "00":
                variants.add(hour)
            for variant in sorted(variants, key=len, reverse=True):
                work = re.sub(rf"(?<![\d./-]){re.escape(variant)}(?![\d./-])", " ", work)
        if schedule.end_time:
            hour = str(int(schedule.end_time.split(":")[0]))
            minute = schedule.end_time.split(":")[1]
            variants = {schedule.end_time, f"{hour}:{minute}", hour}
            if minute == "00":
                variants.add(hour)
            for variant in sorted(variants, key=len, reverse=True):
                work = re.sub(rf"(?<![\d./-]){re.escape(variant)}(?![\d./-])", " ", work)
    work = re.sub(r"\s+", " ", work).strip(" :-–—\t")
    return work or None


def extract_schedule_from_text(text: str, schedule: ParsedScheduleFragments) -> None:
    if not text:
        return
    normalized = normalize_text(text)
    for alias, day_key in RELATIVE_DAY_LOOKUP:
        if normalized == alias or normalized.endswith(" " + alias):
            schedule.relative_day = day_key
            break
        prefix = alias + " "
        if normalized.startswith(prefix) and schedule_rest_after_relative_day(
            normalized[len(prefix) :]
        ):
            schedule.relative_day = day_key
            break
        if f" {alias} " in f" {normalized} ":
            after = normalized.split(alias, 1)[-1].strip()
            if not after or schedule_rest_after_relative_day(after):
                schedule.relative_day = day_key
                break

    abs_date = _ABS_DATE_RE.search(normalized)
    if abs_date and not schedule.date:
        schedule.date = abs_date.group(1)

    range_match = find_time_range(normalized)
    if range_match:
        start = normalize_time_token(range_match.group("start"))
        end = normalize_time_token(range_match.group("end"))
        if start:
            schedule.start_time = start
        if end:
            schedule.end_time = end
        return

    work = normalized
    if schedule.relative_day:
        for alias, day_key in RELATIVE_DAY_LOOKUP:
            if day_key == schedule.relative_day and alias in work:
                work = work.replace(alias, " ", 1).strip()
                break
        work = _strip_time_particles(work)

    if schedule.relative_day or schedule.date or len(work) <= 8:
        token = _TIME_TOKEN_RE.search(work)
        if token and not schedule.start_time:
            schedule.start_time = normalize_time_token(token.group(1))


def apply_start_value(schedule: ParsedScheduleFragments, value: str) -> None:
    text = normalize_text(value)
    for alias, day_key in RELATIVE_DAY_LOOKUP:
        if alias in text:
            schedule.relative_day = day_key
            text = text.replace(alias, " ").strip()
            break
    text = _strip_time_particles(text)
    abs_date = _ABS_DATE_RE.search(text)
    if abs_date:
        schedule.date = abs_date.group(1)
        text = text.replace(abs_date.group(1), " ").strip()
    range_match = find_time_range(text)
    if range_match and apply_time_range(schedule, range_match):
        return
    time_token = _TIME_TOKEN_RE.search(text)
    if time_token:
        schedule.start_time = normalize_time_token(time_token.group(1))


def apply_date_value(schedule: ParsedScheduleFragments, value: str) -> None:
    text = normalize_text(value)
    for alias, day_key in RELATIVE_DAY_LOOKUP:
        if text == alias or text.startswith(alias + " "):
            rest = text[len(alias) :].strip()
            if text == alias or schedule_rest_after_relative_day(rest):
                schedule.relative_day = day_key
                text = rest
                break
    abs_date = _ABS_DATE_RE.search(text)
    if abs_date:
        schedule.date = abs_date.group(1)


def apply_time_value(schedule: ParsedScheduleFragments, value: str) -> None:
    text = normalize_text(value)
    for alias, day_key in RELATIVE_DAY_LOOKUP:
        if text == alias or text.startswith(alias + " ") or f" {alias} " in f" {text} ":
            schedule.relative_day = schedule.relative_day or day_key
            text = text.replace(alias, " ").strip()
            break
    text = _strip_time_particles(text)
    range_match = find_time_range(text)
    if range_match:
        start = normalize_time_token(range_match.group("start"))
        end = normalize_time_token(range_match.group("end"))
        if start:
            schedule.start_time = start
        if end:
            schedule.end_time = end
        return
    token = _TIME_TOKEN_RE.search(text)
    if token:
        schedule.start_time = normalize_time_token(token.group(1))


def try_parse_inline_schedule(line: str, schedule: ParsedScheduleFragments) -> bool:
    text = normalize_text(line)
    matched = False
    for alias, day_key in RELATIVE_DAY_LOOKUP:
        if text == alias:
            schedule.relative_day = day_key
            matched = True
            text = ""
            break
        prefix = alias + " "
        if text.startswith(prefix):
            rest = text[len(prefix) :].strip()
            if not schedule_rest_after_relative_day(rest):
                continue
            schedule.relative_day = day_key
            matched = True
            text = _strip_time_particles(rest)
            break
    range_match = find_time_range(text)
    if range_match and apply_time_range(schedule, range_match):
        return True
    if matched:
        time_token = _TIME_TOKEN_RE.search(text)
        if time_token:
            normalized = normalize_time_token(time_token.group(1))
            if normalized:
                schedule.start_time = normalized
        return True
    # bare "17:00", "17", "14 00"
    if _TIME_TOKEN_RE.fullmatch(text.strip()):
        normalized = normalize_time_token(text.strip())
        if normalized:
            schedule.start_time = normalized
            return True
    return False
