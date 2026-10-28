from datetime import datetime, timedelta
from uuid import UUID

from advertiser_blogger.application.common.exceptions.application_error import CartFullError
from advertiser_blogger.application.common.use_case import UseCase
from advertiser_blogger.application.interactors_bot.project_create.fill_common_cart.dto import (
    FillCommonCartChannel,
    FillCommonCartInput,
)
from advertiser_blogger.application.interactors_bot.project_create.fill_common_cart.interface import DbGateway
from advertiser_blogger.domain.record.cart.entities.common_cart import (
    CommonCart,
    CommonChannelCartOperation,
)
from advertiser_blogger.domain.record.cart.services.common_cart_service import CommonCartService
from advertiser_blogger.domain.record.channel.constants import ChannelStatus


class FillCommonCartInteractor(UseCase[FillCommonCartInput, None]):
    def __init__(self, db_gateway: DbGateway, common_cart_service: CommonCartService):
        self.db_gateway = db_gateway
        self.common_cart_service = common_cart_service

    async def __call__(self, data: FillCommonCartInput) -> None:
        unique = _unique_by_channel_id(data.channels)
        cart = CommonCart(user_id=data.user_id, channels=[])
        total = len(unique)
        await _progress(data.on_progress, 0, total)
        base_created = datetime.utcnow()
        for index, channel in enumerate(unique):
            added = self.common_cart_service.add_channel(
                cart=cart,
                channel=CommonChannelCartOperation(
                    channel_id=channel.channel_id,
                    format=channel.format,
                    match=channel.match,
                    status=ChannelStatus.active,
                    created=base_created + timedelta(microseconds=index),
                ),
            )
            if not added:
                raise CartFullError(message="Cart more than 50 channels is unavailable")
            await _progress(data.on_progress, index + 1, total)

        await self.db_gateway.clear_common_cart(user_id=data.user_id)
        await self.db_gateway.record_common_cart(cart=cart)
        await self.db_gateway.commit()


def _unique_by_channel_id(channels: list[FillCommonCartChannel]) -> list[FillCommonCartChannel]:
    by_id: dict[UUID, FillCommonCartChannel] = {}
    for channel in channels:
        by_id[channel.channel_id] = channel
    return list(by_id.values())


async def _progress(callback, current: int, total: int) -> None:
    if callback is None:
        return
    try:
        await callback(current, total)
    except Exception:
        return
