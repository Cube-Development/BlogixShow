from typing import Protocol
from uuid import UUID

from advertiser_blogger.domain.record.order.entities.order import Project


class CollectCreateorderAuthGateway(Protocol):
    async def get_project(self, project_id: UUID) -> Project | None:
        ...

    async def get_tariff_id_by_project_id(self, project_id: UUID) -> UUID | None:
        ...

    async def get_user_by_id(self, user_id: UUID):
        ...

    async def exists_orders_in_project(self, project_id: UUID, orders: list[UUID]) -> list[UUID]:
        ...

    async def get_project_order_ids(self, project_id: UUID) -> list[UUID]:
        ...

    async def close(self) -> None:
        ...
