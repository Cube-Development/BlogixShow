from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from advertiser_blogger.application.common.exceptions.application_error import EmptyCommonCart, InvalidChannelFormat
from advertiser_blogger.application.interactors_bot.project_create.create_project_from_cart.dto import (
    CreateProjectFromCartInput,
)
from advertiser_blogger.application.interactors_bot.project_create.create_project_from_cart.use_case import (
    CreateProjectFromCartInteractor,
)
from advertiser_blogger.domain.record.cart.entities.common_cart import (
    CommonCart,
    CommonChannelCartOperation,
)
from advertiser_blogger.domain.record.channel.constants import ChannelStatus, Format
from advertiser_blogger.domain.record.order.services.project_service import ProjectService


def _channel(status=ChannelStatus.active) -> CommonChannelCartOperation:
    return CommonChannelCartOperation(
        channel_id=uuid4(),
        format=Format.telegram_1_24,
        match=None,
        status=status,
    )


def test_create_project_from_cart_flush_after_each_order():
    import asyncio

    user_id = uuid4()
    ch1 = _channel()
    ch2 = _channel()
    gw = MagicMock()
    gw.get_common_cart = AsyncMock(return_value=CommonCart(user_id=user_id, channels=[ch1, ch2]))
    gw.get_order_executor_id = AsyncMock(return_value=uuid4())
    gw.get_channel_formats = AsyncMock(return_value=[Format.telegram_1_24])
    gw.create_project = AsyncMock()
    gw.flush = AsyncMock()
    gw.create_project_identifier = AsyncMock()
    gw.create_order = AsyncMock()
    gw.create_order_identifier = AsyncMock()
    gw.commit = AsyncMock()

    interactor = CreateProjectFromCartInteractor(db_gateway=gw, project_service=ProjectService())
    ticks: list[tuple[int, int]] = []

    async def on_progress(current: int, total: int) -> None:
        ticks.append((current, total))

    out = asyncio.run(
        interactor(
            CreateProjectFromCartInput(user_id=user_id, project_name="Sale", on_progress=on_progress)
        )
    )
    assert out.project_id is not None
    assert len(out.orders) == 2
    assert {o.channel_id for o in out.orders} == {ch1.channel_id, ch2.channel_id}
    assert gw.flush.await_count == 3
    gw.commit.assert_awaited_once()
    assert gw.create_order.await_count == 2
    assert gw.create_order_identifier.await_count == 2
    assert ticks[0] == (0, 2)
    assert ticks[-1] == (2, 2)
    project = gw.create_project.await_args.kwargs["project"]
    assert project.name == "Sale"


def test_create_project_from_cart_empty_raises_without_write():
    import asyncio

    gw = MagicMock()
    gw.get_common_cart = AsyncMock(
        return_value=CommonCart(user_id=uuid4(), channels=[_channel(ChannelStatus.inactive)]),
    )
    gw.create_project = AsyncMock()
    gw.commit = AsyncMock()
    interactor = CreateProjectFromCartInteractor(db_gateway=gw, project_service=ProjectService())
    with pytest.raises(EmptyCommonCart):
        asyncio.run(interactor(CreateProjectFromCartInput(user_id=uuid4())))
    gw.create_project.assert_not_awaited()
    gw.commit.assert_not_awaited()


def test_create_project_from_cart_unavailable_format_raises_without_write():
    import asyncio

    ch_ok = _channel()
    ch_bad = _channel()
    gw = MagicMock()
    gw.get_common_cart = AsyncMock(return_value=CommonCart(user_id=uuid4(), channels=[ch_ok, ch_bad]))
    gw.get_channel_formats = AsyncMock(
        side_effect=lambda channel_id: [Format.telegram_1_24] if channel_id == ch_ok.channel_id else [],
    )
    gw.create_project = AsyncMock()
    gw.commit = AsyncMock()
    interactor = CreateProjectFromCartInteractor(db_gateway=gw, project_service=ProjectService())
    with pytest.raises(InvalidChannelFormat) as exc:
        asyncio.run(interactor(CreateProjectFromCartInput(user_id=uuid4())))
    assert exc.value.value == str(ch_bad.channel_id)
    gw.create_project.assert_not_awaited()
    gw.commit.assert_not_awaited()
