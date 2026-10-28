from datetime import date, datetime, time, timedelta

from advertiser_blogger.application.common.constants import Timezone


def tashkent_now() -> datetime:
    return datetime.utcnow() + timedelta(hours=Timezone.TASHKENT.value)


def resolve_clone_date(source_date: date, today: date, time_from: time, now_time: time) -> date:
    """Deterministic clone date rule (no calendar scan, no nearest-free-day search).

    A: source < today               -> tomorrow
    B: source == today, time passed -> tomorrow
    C: source == today, not passed  -> today
    D: source > today               -> source date (unchanged)
    """
    if source_date < today:
        return today + timedelta(days=1)
    if source_date == today:
        if now_time >= time_from:
            return today + timedelta(days=1)
        return today
    return source_date


def resolve_clone_interval(
        date_from: date, date_to: date, today: date, time_from: time, now_time: time,
) -> tuple[date, date]:
    """Shift the whole interval by the same offset the start date is moved by; duration preserved."""
    new_from = resolve_clone_date(source_date=date_from, today=today, time_from=time_from, now_time=now_time)
    offset = new_from - date_from
    return new_from, date_to + offset
