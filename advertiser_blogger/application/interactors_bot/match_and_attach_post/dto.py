from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from advertiser_blogger.application.interactors_bot.publish_post_broadcast.dto import PublishPostFailureReason


MatchSource = Literal["channel_bot", "userbot_scheduled", "blogger_submission"]


@dataclass(frozen=True)
class MatchSuccess:
    order_id: UUID
    score: float


@dataclass(frozen=True)
class MatchNoOrders:
    pass


@dataclass(frozen=True)
class MatchLowSimilarity:
    best_score: float
    order_id: UUID | None


@dataclass(frozen=True)
class MatchPublishFailed:
    order_id: UUID
    score: float
    reason: PublishPostFailureReason | None


@dataclass(frozen=True)
class MatchAlreadyPublished:
    order_id: UUID


MatchAndAttachPostResult = (
    MatchSuccess | MatchNoOrders | MatchLowSimilarity | MatchPublishFailed | MatchAlreadyPublished
)


@dataclass(frozen=True)
class MatchAndAttachPostDtoInput:
    source: MatchSource
    user_id: UUID
    telegram_id: int
    post_url: str
    submitted_text: str
    order_id: UUID | None = None
    channel_ident: int | None = None
    project_id: UUID | None = None
