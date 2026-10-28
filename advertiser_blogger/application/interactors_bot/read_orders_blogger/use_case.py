from advertiser_blogger.application.common.constants import Timezone
from typing import Optional
from uuid import UUID
from datetime import date, datetime, time, timedelta

from advertiser_blogger.application.common.exceptions.application_error import PaginationError
from advertiser_blogger.application.common.use_case import UseCase
from advertiser_blogger.application.interactors_bot.read_orders_blogger.dto import (
    ReadOrdersBloggerDtoInput, ReadOrdersBloggerDtoOutput, ProjectPostBlogger,
)
from advertiser_blogger.application.interactors_bot.read_orders_blogger.interface import DbGateway, ObjStorage
from advertiser_blogger.domain.read.common.services.pagination import PaginationService
from advertiser_blogger.domain.read.post.entities import FileViewWithUrl
from advertiser_blogger.domain.record.order.constants import OrderStatus
from advertiser_blogger.domain.record.order.services.post_service import PostService


class ReadOrdersBloggerInteractor(UseCase[ReadOrdersBloggerDtoInput, ReadOrdersBloggerDtoOutput]):
    def __init__(
            self, db_gateway: DbGateway, pagination_service: PaginationService,
            obj_storage: ObjStorage, post_service: PostService,
    ):
        self.db_gateway = db_gateway
        self.pagination_service = pagination_service
        self.obj_storage = obj_storage
        self.post_service = post_service

    async def __call__(self, data: ReadOrdersBloggerDtoInput) -> ReadOrdersBloggerDtoOutput:
        if data.only_in_progress is True:
            order_status = [OrderStatus.wait, OrderStatus.in_progress]
        else:
            order_status = None
        if data.on_date is not None:
            on_date = data.on_date
        else:
            on_date = (datetime.utcnow() + timedelta(hours=Timezone.TASHKENT)).date()
        count_elements = await self.db_gateway.count_posts(project_id=data.project_id, order_status=order_status)
        try:
            if data.page == 1 and data.elements_on_page is None:
                pagination = self.pagination_service.offset_pagination(
                    page=data.page, elements_on_page=count_elements,
                )
            else:
                pagination = self.pagination_service.offset_pagination(
                    page=data.page, elements_on_page=data.elements_on_page,
                )
        except PaginationError as ex:
            await self.db_gateway.close()
            raise PaginationError(message=ex.message)
        cut = await self.db_gateway.read_uuid_posts_cut(
            project_id=data.project_id, offset=pagination.offset, limit=pagination.limit,
            order_status=order_status,
        )
        if len(cut) == 0:
            await self.db_gateway.close()
            return ReadOrdersBloggerDtoOutput(
                page=data.page, elements=count_elements, posts=[], completed=True,
            )
        posts = []
        for post_id in cut:
            post = await self.read_post(
                user_id=data.user_id, post_id=post_id, order_status=order_status, on_date=on_date,
            )
            if post is None:
                continue
            else:
                posts.append(post)
        await self.db_gateway.close()
        return ReadOrdersBloggerDtoOutput(
            page=data.page, elements=count_elements, posts=posts, completed=False,
        )

    async def read_post(
            self,
            user_id: UUID,
            post_id: UUID,
            on_date: date,
            order_status: list[OrderStatus] = None,
    ) -> ProjectPostBlogger | None:
        current_datetime = datetime.combine(on_date, time.min)
        post = await self.db_gateway.read_blogger_orders_by_post_id(
            user_id=user_id, post_id=post_id, order_status=order_status, current_datetime=current_datetime,
        )
        if post is None:
            return
        file_list = []
        for file in post.files:
            file_url = await self.obj_storage.presigned_get(key=file.content)
            file_list.append(
                FileViewWithUrl(
                    content_type=file.content_type, content=file_url,
                    name=file.name,
                )
            )
        for text in post.text:
            file_list.append(
                FileViewWithUrl(
                    content_type=text.content_type, content=text.content, name=None,
                )
            )
        for button in post.buttons:
            file_list.append(
                FileViewWithUrl(
                    content_type=button.content_type, content=button.content,
                    name=None, url=button.url,
                )
            )
        await self.db_gateway.close()
        return ProjectPostBlogger(
            id=post.id, match_type=post.match_type, orders=post.orders,
            platform=post.platform, comment=post.comment, files=file_list,
            post_type=self.post_service.map_format_to_post_type(format=post.format),
        )
