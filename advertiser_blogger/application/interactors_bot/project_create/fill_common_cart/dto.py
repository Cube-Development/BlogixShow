from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from advertiser_blogger.domain.record.channel.constants import Format

FillCartProgressCallback = Callable[[int, int], Awaitable[None]]


@dataclass(frozen=True)
class FillCommonCartChannel:
    channel_id: UUID
    format: Format
    match: float | None = None


@dataclass
class FillCommonCartInput:
    user_id: UUID
    channels: list[FillCommonCartChannel]
    on_progress: FillCartProgressCallback | None = None
