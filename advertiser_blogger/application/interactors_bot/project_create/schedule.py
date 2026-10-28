from __future__ import annotations

from datetime import datetime, timedelta, time, date, timezone as dt_timezone

from advertiser_blogger.application.interactors_bot.project_create.models import (
    ParsedScheduleFragments,
    ProjectSchedule,
    ScheduleSource,
)

DEFAULT_TIMEZONE = "Asia/Tashkent"
DEFAULT_DURATION_HOURS = 2
SLOT_MINUTES = 5

# Asia/Tashkent is UTC+5 without DST — avoid ZoneInfo/tzdata dependency on Windows.
TASHKENT_TZ = dt_timezone(timedelta(hours=5), name="Asia/Tashkent")


class PastScheduleError(ValueError):
    """Raised when resolved start_at is in the past."""


def _get_tz(timezone: str):
    if timezone == "Asia/Tashkent":
        return TASHKENT_TZ
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(timezone)
    except Exception:
        return TASHKENT_TZ


def ceil_to_slot(dt: datetime, slot_minutes: int = SLOT_MINUTES) -> datetime:
    if slot_minutes <= 0:
        return dt
    dt = dt.replace(second=0, microsecond=0)
    remainder = dt.minute % slot_minutes
    if remainder == 0:
        return dt
    delta = slot_minutes - remainder
    return dt + timedelta(minutes=delta)


def resolve_project_schedule(
        fragments: ParsedScheduleFragments | None,
        *,
        now: datetime | None = None,
        timezone: str = DEFAULT_TIMEZONE,
        default_duration_hours: int = DEFAULT_DURATION_HOURS,
        slot_minutes: int = SLOT_MINUTES,
        allow_past: bool = False,
) -> ProjectSchedule:
    tz = _get_tz(timezone)
    current = now if now is not None else datetime.now(tz=tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    else:
        current = current.astimezone(tz)

    fr = fragments or ParsedScheduleFragments()
    has_user_time = bool(fr.start_time or fr.end_time or fr.date or fr.relative_day)

    if not has_user_time:
        start = ceil_to_slot(current, slot_minutes=slot_minutes)
        end = start + timedelta(hours=default_duration_hours)
        return ProjectSchedule(start_at=start, end_at=end, source=ScheduleSource.default_generated)

    target_date = _resolve_date(fr, current=current)

    if fr.start_time:
        start = datetime.combine(target_date, _parse_clock(fr.start_time), tzinfo=tz)
    elif fr.relative_day or fr.date:
        rounded = ceil_to_slot(current, slot_minutes=slot_minutes)
        start = datetime.combine(target_date, rounded.time(), tzinfo=tz)
    else:
        start = ceil_to_slot(current, slot_minutes=slot_minutes)

    if fr.end_time:
        end_clock = _parse_clock(fr.end_time)
        end = datetime.combine(target_date, end_clock, tzinfo=tz)
        if end <= start:
            end = end + timedelta(days=1)
    else:
        end = start + timedelta(hours=default_duration_hours)

    if not allow_past and start < current:
        raise PastScheduleError(f"Schedule start_at {start.isoformat()} is in the past")

    source = ScheduleSource.user_defined
    if not fr.start_time and not fr.end_time:
        source = ScheduleSource.default_generated

    return ProjectSchedule(start_at=start, end_at=end, source=source)


def _resolve_date(fr: ParsedScheduleFragments, *, current: datetime) -> date:
    if fr.relative_day == "today":
        return current.date()
    if fr.relative_day == "tomorrow":
        return current.date() + timedelta(days=1)
    if fr.relative_day == "day_after":
        return current.date() + timedelta(days=2)
    if fr.date:
        return _parse_abs_date(fr.date, year_hint=current.year)
    return current.date()


def _parse_abs_date(raw: str, *, year_hint: int) -> date:
    cleaned = raw.replace("/", ".")
    parts = cleaned.split(".")
    if len(parts) == 2:
        day, month = int(parts[0]), int(parts[1])
        return date(year_hint, month, day)
    if len(parts) == 3:
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        if year < 100:
            year += 2000
        return date(year, month, day)
    raise ValueError(f"Invalid date: {raw}")


def _parse_clock(raw: str) -> time:
    hour_s, minute_s = raw.split(":")
    return time(hour=int(hour_s), minute=int(minute_s))
