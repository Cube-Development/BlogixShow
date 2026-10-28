"""RU/UZ alias dictionary for structured project-create replies."""

from __future__ import annotations

ALIASES: dict[str, tuple[str, ...]] = {
    "project": (
        "проект",
        "проэкт",
        "название проекта",
        "loyiha",
        "loyiha nomi",
        "proyekt",
    ),
    "comment": (
        "комментарий",
        "коммент",
        "примечание",
        "описание",
        "izoh",
        "kommentariya",
        "tavsif",
    ),
    "start_time": (
        "время",
        "старт",
        "начало",
        "с",
        "vaqt",
        "boshlanish",
        "start",
        "dan",
    ),
    "end_time": (
        "конец",
        "окончание",
        "до",
        "tugash",
        "yakun",
        "gacha",
    ),
    "channels": (
        "каналы",
        "канал",
        "channels",
        "kanallar",
        "kanal",
    ),
}

RELATIVE_DAY_ALIASES: dict[str, tuple[str, ...]] = {
    "today": ("сегодня", "bugun"),
    "tomorrow": ("завтра", "ertaga"),
    "day_after": ("послезавтра", "indinga"),
}


def build_alias_lookup() -> list[tuple[str, str]]:
    """Return (alias, field_key) sorted by alias length descending (longest match first)."""
    items: list[tuple[str, str]] = []
    for field_key, aliases in ALIASES.items():
        for alias in aliases:
            items.append((alias, field_key))
    items.sort(key=lambda x: len(x[0]), reverse=True)
    return items


def build_relative_day_lookup() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for day_key, aliases in RELATIVE_DAY_ALIASES.items():
        for alias in aliases:
            items.append((alias, day_key))
    items.sort(key=lambda x: len(x[0]), reverse=True)
    return items


ALIAS_LOOKUP = build_alias_lookup()
RELATIVE_DAY_LOOKUP = build_relative_day_lookup()
