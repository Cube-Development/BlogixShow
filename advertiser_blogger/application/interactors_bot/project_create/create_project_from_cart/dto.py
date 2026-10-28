from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

CreateOrdersProgressCallback = Callable[[int, int], Awaitable[None]]


@dataclass(frozen=True)
class ProjectOrderRef:
    id: UUID
    channel_id: UUID


@dataclass
class CreateProjectFromCartInput:
    user_id: UUID
    project_name: str | None = None
    on_progress: CreateOrdersProgressCallback | None = None


@dataclass
class CreateProjectFromCartOutput:
    project_id: UUID
    orders: list[ProjectOrderRef]
