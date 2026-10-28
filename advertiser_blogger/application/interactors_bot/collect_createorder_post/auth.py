from __future__ import annotations

from uuid import UUID

from advertiser_blogger.application.common.exceptions.application_error import (
    AccessDenied,
    ManagerNotFound,
    OrderNotFound,
    ProjectNotFound,
)
from advertiser_blogger.application.interactors_bot.collect_createorder_post.interface import (
    CollectCreateorderAuthGateway,
)
from advertiser_blogger.domain.read.constants import Role


async def assert_collect_createorder_access(
        gateway: CollectCreateorderAuthGateway,
        *,
        user_id: UUID,
        project_id: UUID,
        order_id: UUID | None,
) -> None:
    # TEMP: skip collect ownership checks for local debugging.
    return
    # project = await gateway.get_project(project_id=project_id)
    # if project is None:
    #     await gateway.close()
    #     raise ProjectNotFound(message="Project not found")
    # owner = await gateway.get_user_by_id(user_id=user_id)
    # if owner is None:
    #     await gateway.close()
    #     raise ManagerNotFound(message="Owner not found")
    # tariff = await gateway.get_tariff_id_by_project_id(project_id=project_id)
    # if tariff is None:
    #     if project.user_id != user_id:
    #         await gateway.close()
    #         raise AccessDenied()
    # else:
    #     if owner.role != Role.manager:
    #         await gateway.close()
    #         raise AccessDenied()
    # if order_id is not None:
    #     exists = await gateway.exists_orders_in_project(project_id=project_id, orders=[order_id])
    #     if len(exists) != 1:
    #         await gateway.close()
    #         raise OrderNotFound(message="Order not found")
