from __future__ import annotations

from advertiser_blogger.application.common.application.post.post_convert import FileObject
from advertiser_blogger.application.common.exceptions.application_error import (
    OrderNotFound,
    OrderToMatchNotFound,
)
from advertiser_blogger.application.interactors_bot.collect_createorder_post.auth import (
    assert_collect_createorder_access,
)
from advertiser_blogger.application.interactors_bot.collect_createorder_post.dto import (
    CollectCreateorderAcceptInput,
)
from advertiser_blogger.application.interactors_bot.collect_createorder_post.interface import (
    CollectCreateorderAuthGateway,
)
from advertiser_blogger.application.interactors_bot.project_create.media_upload import (
    ProjectPostMediaUploader,
)
from advertiser_blogger.application.interactors_bot.project_create.models import PublishMode
from advertiser_blogger.application.record.create_post_custom_orders.dto import CreatePostCustomOrderDtoInput
from advertiser_blogger.application.record.create_post_custom_orders.use_case import CreatePostCustomOrders
from advertiser_blogger.domain.record.order.constants import PostMatchType


class CollectCreateorderAcceptPost:
    def __init__(
            self,
            auth_gateway: CollectCreateorderAuthGateway,
            media_uploader: ProjectPostMediaUploader,
            create_post_custom_orders: CreatePostCustomOrders,
    ):
        self.auth_gateway = auth_gateway
        self.media_uploader = media_uploader
        self.create_post_custom_orders = create_post_custom_orders

    async def __call__(self, data: CollectCreateorderAcceptInput) -> None:
        await assert_collect_createorder_access(
            self.auth_gateway,
            user_id=data.user_id,
            project_id=data.project_id,
            order_id=data.order_id,
        )
        files: list[FileObject] = await self.media_uploader(
            data.post,
            telegram_chat_id=data.telegram_chat_id,
            publish_mode=PublishMode.copy,
        )
        if data.order_id is not None:
            exists = await self.auth_gateway.exists_orders_in_project(
                project_id=data.project_id,
                orders=[data.order_id],
            )
            order_in_project = len(exists) == 1
            if not order_in_project:
                await self.auth_gateway.close()
                raise OrderNotFound(message="Order not found")
            order_ids = [data.order_id]
            match_type = PostMatchType.individual
        else:
            order_ids = list(await self.auth_gateway.get_project_order_ids(project_id=data.project_id))
            if not order_ids:
                await self.auth_gateway.close()
                raise OrderToMatchNotFound(message="Post to match not found")
            match_type = PostMatchType.universal
        await self.create_post_custom_orders(
            data=CreatePostCustomOrderDtoInput(
                user_id=data.user_id,
                project_id=data.project_id,
                comment=None,
                files=files,
                orders=order_ids,
                match_type=match_type,
            ),
        )
