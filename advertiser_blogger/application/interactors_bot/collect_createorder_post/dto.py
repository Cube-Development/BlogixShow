from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from advertiser_blogger.application.interactors_bot.project_create.models import BotPostDraft


@dataclass(frozen=True)
class CollectCreateorderAcceptInput:
    user_id: UUID
    telegram_chat_id: int
    project_id: UUID
    order_id: UUID | None
    post: BotPostDraft
