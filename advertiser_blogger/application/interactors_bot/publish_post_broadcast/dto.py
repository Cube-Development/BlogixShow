from dataclasses import dataclass
from enum import Enum
from typing import Optional
from uuid import UUID


class PublishPostFailureReason(str, Enum):
    order_not_found = "order_not_found"
    channel_not_found = "channel_not_found"
    access_denied = "access_denied"
    invalid_status = "invalid_status"
    already_published = "already_published"
    order_expired = "order_expired"
    date_out_of_interval = "date_out_of_interval"
    date_or_time_not_setup = "date_or_time_not_setup"
    outside_time_window = "outside_time_window"
    post_not_found = "post_not_found"


@dataclass
class PublishObject:
    order_id: UUID
    post_url: str


@dataclass
class PublishPostBroadcastDtoInput:
    user_id: UUID
    telegram_id: int
    posts: list[PublishObject]


@dataclass
class PublishPostResult:
    order_id: UUID
    post_url: str
    success: bool
    reason: Optional[PublishPostFailureReason] = None


@dataclass
class PublishPostBroadcastDtoOutput:
    results: list[PublishPostResult]
