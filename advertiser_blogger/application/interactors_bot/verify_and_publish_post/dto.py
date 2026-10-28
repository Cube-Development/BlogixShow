from dataclasses import dataclass
from uuid import UUID

from advertiser_blogger.application.interactors_bot.publish_post_broadcast.dto import PublishPostFailureReason
from advertiser_blogger.presentation.bot.common.extract_post_submission import PostSubmissionInput


@dataclass(frozen=True)
class Success:
    order_id: UUID
    score: float


@dataclass(frozen=True)
class NoOrders:
    pass


@dataclass(frozen=True)
class TextUnavailable:
    post_url: str


@dataclass(frozen=True)
class LowSimilarity:
    best_score: float
    order_id: UUID | None


@dataclass(frozen=True)
class PublishFailed:
    order_id: UUID
    score: float
    reason: PublishPostFailureReason | None


VerifyResult = Success | NoOrders | TextUnavailable | LowSimilarity | PublishFailed


@dataclass(frozen=True)
class VerifyAndPublishPostDtoInput:
    user_id: UUID
    telegram_id: int
    submission: PostSubmissionInput
    project_id: UUID | None = None
