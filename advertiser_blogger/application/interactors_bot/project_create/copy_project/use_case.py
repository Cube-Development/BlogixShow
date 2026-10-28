from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from uuid import UUID, uuid4

from advertiser_blogger.application.common.exceptions.application_error import (
    AccessDenied,
    ButtonNeedUrl,
    CalendarDayIsBusy,
    DateOrTimeNotSetup,
    EmptyProjectCart,
    ProjectNotFound,
)
from advertiser_blogger.application.common.use_case import UseCase
from advertiser_blogger.application.interactors_bot.project_create.copy_project.date_resolver import (
    resolve_clone_date,
    resolve_clone_interval,
    tashkent_now,
)
from advertiser_blogger.application.interactors_bot.project_create.copy_project.dto import (
    CopyProjectInput,
    CopyProjectOutput,
)
from advertiser_blogger.application.interactors_bot.project_create.copy_project.interface import DbGateway
from advertiser_blogger.domain.record.cart.entities.common_cart import CommonChannelCartOperation
from advertiser_blogger.domain.record.cart.entities.project_cart import ProjectChannelCart
from advertiser_blogger.domain.record.cart.services.project_cart_service import ProjectCartService
from advertiser_blogger.domain.record.channel.constants import ChannelStatus, Format
from advertiser_blogger.domain.record.order.constants import ContentType, OrderStatus, ProjectStatus
from advertiser_blogger.domain.record.order.entities.order import Post
from advertiser_blogger.domain.record.order.services.post_service import PostService
from advertiser_blogger.domain.record.order.services.project_service import ProjectService
from advertiser_blogger.domain.record.wallet.services.wallet import WalletService

_ALLOWED_STATUSES = (
    ChannelStatus.active,
    ChannelStatus.re_moderation,
    ChannelStatus.invalid_url,
)


@dataclass
class _ClonedOrder:
    new_order_id: UUID
    source_order_id: UUID
    channel_id: UUID
    format: Format
    channel_status: ChannelStatus


class CopyProjectInteractor(UseCase[CopyProjectInput, CopyProjectOutput]):
    """Clone an existing project into a new `saved` one without touching the source or the common cart."""

    def __init__(
            self,
            db_gateway: DbGateway,
            project_service: ProjectService,
            post_service: PostService,
            wallet_service: WalletService,
            project_cart_service: ProjectCartService,
            now_provider: Callable[[], datetime] = tashkent_now,
    ):
        self.db_gateway = db_gateway
        self.project_service = project_service
        self.post_service = post_service
        self.wallet_service = wallet_service
        self.project_cart_service = project_cart_service
        self._now_provider = now_provider

    async def __call__(self, data: CopyProjectInput) -> CopyProjectOutput:
        source = await self.db_gateway.get_project(project_id=data.project_id)
        if source is None:
            await self.db_gateway.close()
            raise ProjectNotFound(message="Project not found")
        if source.user_id != data.user_id:
            await self.db_gateway.close()
            raise AccessDenied()

        try:
            project_id, cloned_orders = await self._clone_project_and_orders(
                source_project_id=data.project_id, source_user_id=source.user_id, source_name=source.name,
            )
            await self._clone_posts(
                source_project_id=data.project_id, project_id=project_id, cloned_orders=cloned_orders,
            )
            await self._clone_dates(cloned_orders=cloned_orders)
            await self._setup_prices(cloned_orders=cloned_orders)
            await self._create_project_cart(
                project_id=project_id, user_id=source.user_id, cloned_orders=cloned_orders,
            )
            await self.db_gateway.change_project_status(project_id=project_id, status=ProjectStatus.saved)
            await self.db_gateway.commit()
        except Exception:
            await self.db_gateway.rollback()
            raise

        return CopyProjectOutput(
            project_id=project_id, order_ids=[order.new_order_id for order in cloned_orders],
        )

    async def _clone_project_and_orders(
            self, source_project_id: UUID, source_user_id: UUID | None, source_name: str,
    ) -> tuple[UUID, list[_ClonedOrder]]:
        source_orders = await self.db_gateway.get_project_orders_readonly(project_id=source_project_id)
        kept_orders: list[tuple] = []
        for source_order in source_orders:
            channel_status = await self.db_gateway.get_channel_status(channel_id=source_order.channel_id)
            if channel_status in _ALLOWED_STATUSES:
                kept_orders.append((source_order, channel_status))
        if not kept_orders:
            await self.db_gateway.close()
            raise EmptyProjectCart(message="No active channels to clone")

        project = self.project_service.create_project(user_id=source_user_id)
        project.name = source_name
        await self.db_gateway.create_project(project=project)
        await self.db_gateway.flush()
        await self.db_gateway.create_project_identifier(
            ident=self.project_service.create_project_identifier(project_id=project.id),
        )

        cloned_orders: list[_ClonedOrder] = []
        for source_order, channel_status in kept_orders:
            executor_id = await self.db_gateway.get_order_executor_id(
                user_id=source_user_id, channel_id=source_order.channel_id,
            )
            order = self.project_service.create_order(
                project_id=project.id,
                executor_id=executor_id,
                channel=CommonChannelCartOperation(
                    channel_id=source_order.channel_id, format=source_order.format,
                    match=None, status=channel_status,
                ),
                created=datetime.utcnow(),
            )
            await self.db_gateway.create_order(order=order)
            await self.db_gateway.flush()
            await self.db_gateway.create_order_identifier(
                ident=self.project_service.create_order_identifier(order_id=order.id),
            )
            cloned_orders.append(
                _ClonedOrder(
                    new_order_id=order.id, source_order_id=source_order.id,
                    channel_id=source_order.channel_id, format=source_order.format,
                    channel_status=channel_status,
                ),
            )
        return project.id, cloned_orders

    async def _clone_posts(
            self, source_project_id: UUID, project_id: UUID, cloned_orders: list[_ClonedOrder],
    ) -> None:
        new_order_by_source = {order.source_order_id: order.new_order_id for order in cloned_orders}
        matched_orders: set[UUID] = set()
        for source_post_id in await self.db_gateway.get_project_post_id(project_id=source_project_id):
            source_post = await self.db_gateway.get_post_full(post_id=source_post_id)
            if source_post is None:
                continue
            source_order_ids = await self.db_gateway.get_post_order_ids(post_id=source_post_id)
            target_order_ids = [
                new_order_by_source[source_order_id]
                for source_order_id in source_order_ids
                if source_order_id in new_order_by_source and new_order_by_source[source_order_id] not in matched_orders
            ]
            if not target_order_ids:
                continue
            post = self.post_service.create_post(
                project_id=project_id, comment=source_post.comment,
                files=source_post.files, match_type=source_post.match_type,
            )
            await self._create_post(post=post)
            await self.db_gateway.flush()
            for order_id in target_order_ids:
                await self.db_gateway.create_order_match(
                    match=self.project_service.match_order_and_post(
                        project_id=project_id, order_id=order_id, post_id=post.id,
                    ),
                )
                await self.db_gateway.change_order_status(order_id=order_id, status=OrderStatus.post_matched)
                matched_orders.add(order_id)
            await self.db_gateway.flush()

    async def _create_post(self, post: Post) -> None:
        await self.db_gateway.create_post(id=post.id, project_id=post.project_id, match_type=post.match_type)
        await self.db_gateway.flush()
        await self.db_gateway.create_post_identificator(post_id=post.id)
        if post.comment:
            await self.db_gateway.create_post_comment(id=uuid4(), post_id=post.id, comment=post.comment)
        for file in post.files:
            if file.content_type == ContentType.text:
                await self.db_gateway.create_post_text(
                    id=uuid4(), post_id=post.id, content=file.content, content_type=ContentType.text,
                )
            elif file.content_type == ContentType.button:
                if file.url is None:
                    await self.db_gateway.close()
                    raise ButtonNeedUrl(message="Button need name and url fields, url field not found")
                await self.db_gateway.create_post_button(
                    id=uuid4(), post_id=post.id, content=file.content,
                    url=file.url, content_type=ContentType.button,
                )
            else:
                await self.db_gateway.create_post_content(
                    id=uuid4(), post_id=post.id, content=file.content, name=file.name,
                    content_type=file.content_type,
                )

    async def _clone_dates(self, cloned_orders: list[_ClonedOrder]) -> None:
        now = self._now_provider()
        today = now.date()
        now_time = now.time()
        for order in cloned_orders:
            time_interval = await self.db_gateway.get_post_time_interval(order_id=order.source_order_id)
            if time_interval is None:
                await self.db_gateway.close()
                raise DateOrTimeNotSetup(message="Source order has no time interval to clone")
            single_date = await self.db_gateway.get_order_date(order_id=order.source_order_id)
            if single_date is not None:
                await self._clone_single_date(
                    order=order, source_date=single_date,
                    today=today, time_from=time_interval.time_from, now_time=now_time,
                )
            else:
                intervals = await self.db_gateway.get_order_dates(order_id=order.source_order_id)
                if not intervals:
                    await self.db_gateway.close()
                    raise DateOrTimeNotSetup(message="Source order has no date to clone")
                await self._clone_interval(
                    order=order, source_interval=intervals[0],
                    today=today, time_from=time_interval.time_from, now_time=now_time,
                )
            await self.db_gateway.create_time_interval(
                time_interval=self.project_service.create_time_interval(
                    order_id=order.new_order_id,
                    time_from=time_interval.time_from, time_to=time_interval.time_to,
                ),
            )

    async def _clone_single_date(self, order, source_date, today, time_from, now_time) -> None:
        chosen = resolve_clone_date(
            source_date=source_date, today=today, time_from=time_from, now_time=now_time,
        )
        if await self.db_gateway.is_busy_calendar_day(order_id=order.new_order_id, day=chosen):
            await self.db_gateway.close()
            raise CalendarDayIsBusy(message="Calendar day is busy")
        await self.db_gateway.create_order_date(
            order_date=self.project_service.create_post_date(order_id=order.new_order_id, post_date=chosen),
        )
        await self.db_gateway.change_order_status(order_id=order.new_order_id, status=OrderStatus.date_constant)

    async def _clone_interval(self, order, source_interval, today, time_from, now_time) -> None:
        date_from, date_to = resolve_clone_interval(
            date_from=source_interval.date_from, date_to=source_interval.date_to,
            today=today, time_from=time_from, now_time=now_time,
        )
        list_days = self.project_service.from_date_interval_to_list(date_from=date_from, date_to=date_to)
        if await self.db_gateway.is_busy_calendar_days(order_id=order.new_order_id, days=list_days) <= 0:
            await self.db_gateway.close()
            raise CalendarDayIsBusy(message="Calendar days is busy")
        await self.db_gateway.create_order_date_interval(
            date_interval=self.project_service.create_date_interval(
                order_id=order.new_order_id, date_from=date_from, date_to=date_to,
            ),
        )
        await self.db_gateway.change_order_status(order_id=order.new_order_id, status=OrderStatus.date_interval)

    async def _setup_prices(self, cloned_orders: list[_ClonedOrder]) -> None:
        for order in cloned_orders:
            channel_price = await self.db_gateway.get_order_advertiser_prices(order_id=order.new_order_id)
            await self.db_gateway.change_order_status(order_id=order.new_order_id, status=OrderStatus.saved)
            if channel_price is None:
                # format was removed by blogger: copy as is, advertiser selects another format before payment
                continue
            order_crushes = self.wallet_service.create_order_crushes(
                blogger_price=channel_price.blogger_price, advertiser_price=channel_price.advertiser_price,
                order_id=order.new_order_id,
            )
            await self.db_gateway.setup_order_price(order_crushes=order_crushes)

    async def _create_project_cart(
            self, project_id: UUID, user_id: UUID | None, cloned_orders: list[_ClonedOrder],
    ) -> None:
        project_cart = await self.db_gateway.get_project_cart(project_id=project_id)
        for order in cloned_orders:
            self.project_cart_service.add_channel(
                cart=project_cart,
                channel=ProjectChannelCart(
                    project_id=project_id, channel_id=order.channel_id, format=order.format,
                    match=None, status=order.channel_status,
                ),
            )
        await self.db_gateway.record_project_cart(cart=project_cart, user_id=user_id)
