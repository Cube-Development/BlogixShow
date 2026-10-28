from datetime import datetime
from typing import Protocol
from uuid import UUID

from advertiser_blogger.application.common.db_interface.record import IsExistPost, Close
from advertiser_blogger.application.interactors_bot.verify_and_publish_post.interface import PostTextProvider
from advertiser_blogger.domain.read.order.entities.order_candidate import OrderCandidate
from advertiser_blogger.domain.record.order.constants import OrderStatus


class ReadDbGateway(Protocol):
    async def read_today_order_candidates_by_channel(
            self,
            executor_id: UUID,
            channel_ident: int,
            current_datetime: datetime,
            order_status: list[OrderStatus] | None = None,
    ) -> list[OrderCandidate]:
        raise NotImplementedError

    async def read_today_order_candidates_by_project(
            self,
            executor_id: UUID,
            project_id: UUID,
            current_datetime: datetime,
            order_status: list[OrderStatus] | None = None,
            channel_ident: int | None = None,
    ) -> list[OrderCandidate]:
        raise NotImplementedError

    async def read_order_candidate_by_order_id(
            self,
            order_id: UUID,
            current_datetime: datetime,
            order_status: list[OrderStatus] | None = None,
    ) -> OrderCandidate | None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


class RecordDbGateway(IsExistPost, Close, Protocol):
    pass


class PostTextProviderGateway(PostTextProvider, Protocol):
    pass
