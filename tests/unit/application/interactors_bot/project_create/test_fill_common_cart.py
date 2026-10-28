import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from advertiser_blogger.application.common.exceptions.application_error import CartFullError
from advertiser_blogger.application.interactors_bot.project_create.fill_common_cart.dto import (
    FillCommonCartChannel,
    FillCommonCartInput,
)
from advertiser_blogger.application.interactors_bot.project_create.fill_common_cart.use_case import (
    FillCommonCartInteractor,
)
from advertiser_blogger.domain.record.cart.services.common_cart_service import CommonCartService
from advertiser_blogger.domain.record.channel.constants import Format


def _interactor(gw=None) -> tuple[FillCommonCartInteractor, MagicMock]:
    gw = gw or MagicMock()
    gw.clear_common_cart = AsyncMock()
    gw.record_common_cart = AsyncMock()
    gw.commit = AsyncMock()
    return FillCommonCartInteractor(db_gateway=gw, common_cart_service=CommonCartService()), gw


def test_fill_dedupes_by_channel_id_and_commits_once():
    interactor, gw = _interactor()
    channel_id = uuid4()
    user_id = uuid4()
    asyncio.run(
        interactor(
            FillCommonCartInput(
                user_id=user_id,
                channels=[
                    FillCommonCartChannel(channel_id=channel_id, format=Format.telegram_24),
                    FillCommonCartChannel(channel_id=channel_id, format=Format.telegram_1_24),
                    FillCommonCartChannel(channel_id=uuid4(), format=Format.telegram_1_24),
                ],
            )
        )
    )
    gw.clear_common_cart.assert_awaited_once_with(user_id=user_id)
    gw.record_common_cart.assert_awaited_once()
    gw.commit.assert_awaited_once()
    cart = gw.record_common_cart.await_args.kwargs["cart"]
    assert cart.user_id == user_id
    assert len(cart.channels) == 2
    kept = next(ch for ch in cart.channels if ch.channel_id == channel_id)
    assert kept.format == Format.telegram_1_24


def test_fill_fifty_ok_fifty_one_raises_without_write():
    interactor, gw = _interactor()
    channels = [
        FillCommonCartChannel(channel_id=uuid4(), format=Format.telegram_1_24)
        for _ in range(50)
    ]
    asyncio.run(interactor(FillCommonCartInput(user_id=uuid4(), channels=channels)))
    assert len(gw.record_common_cart.await_args.kwargs["cart"].channels) == 50

    interactor, gw = _interactor()
    channels.append(FillCommonCartChannel(channel_id=uuid4(), format=Format.telegram_1_24))
    with pytest.raises(CartFullError):
        asyncio.run(interactor(FillCommonCartInput(user_id=uuid4(), channels=channels)))
    gw.clear_common_cart.assert_not_awaited()
    gw.record_common_cart.assert_not_awaited()
    gw.commit.assert_not_awaited()
