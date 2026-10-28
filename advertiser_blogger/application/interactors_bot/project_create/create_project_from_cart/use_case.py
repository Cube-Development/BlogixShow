from advertiser_blogger.application.common.application.channel_format import (
    find_channels_with_invalid_format, invalid_channels_value,
)
from advertiser_blogger.application.common.exceptions.application_error import EmptyCommonCart, InvalidChannelFormat
from advertiser_blogger.application.common.use_case import UseCase
from advertiser_blogger.application.interactors_bot.project_create.create_project_from_cart.dto import (
    CreateProjectFromCartInput,
    CreateProjectFromCartOutput,
    ProjectOrderRef,
)
from advertiser_blogger.application.interactors_bot.project_create.create_project_from_cart.interface import DbGateway
from advertiser_blogger.domain.record.channel.constants import ChannelStatus
from advertiser_blogger.domain.record.order.services.project_service import ProjectService

_ALLOWED_STATUSES = (
    ChannelStatus.active,
    ChannelStatus.re_moderation,
    ChannelStatus.invalid_url,
)


class CreateProjectFromCartInteractor(UseCase[CreateProjectFromCartInput, CreateProjectFromCartOutput]):
    def __init__(self, db_gateway: DbGateway, project_service: ProjectService):
        self.db_gateway = db_gateway
        self.project_service = project_service

    async def __call__(self, data: CreateProjectFromCartInput) -> CreateProjectFromCartOutput:
        common_cart = await self.db_gateway.get_common_cart(user_id=data.user_id)
        channels = [ch for ch in common_cart.channels if ch.status in _ALLOWED_STATUSES]
        if not channels:
            raise EmptyCommonCart(message="Empty common cart")
        invalid_channels = await find_channels_with_invalid_format(db_gateway=self.db_gateway, channels=channels)
        if invalid_channels:
            raise InvalidChannelFormat(
                message="Channel format is not available, select another format",
                value=invalid_channels_value(invalid_channels),
            )

        total = len(channels)
        await _progress(data.on_progress, 0, total)

        project = self.project_service.create_project(user_id=data.user_id)
        if data.project_name:
            project.name = data.project_name
        await self.db_gateway.create_project(project=project)
        await self.db_gateway.flush()
        await self.db_gateway.create_project_identifier(
            ident=self.project_service.create_project_identifier(project_id=project.id),
        )

        orders: list[ProjectOrderRef] = []
        for index, channel in enumerate(channels):
            executor_id = await self.db_gateway.get_order_executor_id(
                user_id=data.user_id, channel_id=channel.channel_id,
            )
            order = self.project_service.create_order(
                project_id=project.id,
                executor_id=executor_id,
                channel=channel,
                created=channel.created,
            )
            await self.db_gateway.create_order(order=order)
            await self.db_gateway.flush()
            await self.db_gateway.create_order_identifier(
                ident=self.project_service.create_order_identifier(order_id=order.id),
            )
            orders.append(ProjectOrderRef(id=order.id, channel_id=channel.channel_id))
            await _progress(data.on_progress, index + 1, total)

        await self.db_gateway.commit()
        return CreateProjectFromCartOutput(project_id=project.id, orders=orders)


async def _progress(callback, current: int, total: int) -> None:
    if callback is None:
        return
    try:
        await callback(current, total)
    except Exception:
        return
