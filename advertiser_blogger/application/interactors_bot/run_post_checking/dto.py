from dataclasses import dataclass, field
from uuid import UUID

from advertiser_blogger.application.events.verify_post_scheduled.dto import VerifyOrderResult


@dataclass(frozen=True)
class RunPostCheckingDtoInput:
    project_ids: list[UUID]


@dataclass(frozen=True)
class PostCheckingCard:
    project_id: UUID
    result: VerifyOrderResult


@dataclass(frozen=True)
class RunPostCheckingDtoOutput:
    header: str
    errors: list[str] = field(default_factory=list)
    cards: list[PostCheckingCard] = field(default_factory=list)
