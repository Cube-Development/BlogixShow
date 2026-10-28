from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from advertiser_blogger.application.interactors_bot.project_create.models import BotProjectDraft

SaveProgressCallback = Callable[[str, int, int], Awaitable[None]]


@dataclass
class CreateSavedProjectFromBotDraftInput:
    draft: BotProjectDraft
    user_id: UUID
    on_progress: SaveProgressCallback | None = None


@dataclass
class CreateSavedProjectFromBotDraftOutput:
    project_id: UUID
    partial: bool = False
    error: str | None = None
