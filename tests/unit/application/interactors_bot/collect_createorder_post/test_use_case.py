from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from advertiser_blogger.application.common.exceptions.application_error import (
    OrderNotFound,
    OrderToMatchNotFound,
)
from advertiser_blogger.application.interactors_bot.collect_createorder_post.dto import (
    CollectCreateorderAcceptInput,
)
from advertiser_blogger.application.interactors_bot.collect_createorder_post.use_case import (
    CollectCreateorderAcceptPost,
)
from advertiser_blogger.application.interactors_bot.project_create.models import BotPostDraft
from advertiser_blogger.domain.read.constants import Role
from advertiser_blogger.domain.record.order.constants import PostMatchType


def _owner_auth(*, user_id, order_ids=None):
    auth = MagicMock()
    auth.close = AsyncMock()
    auth.get_project = AsyncMock(return_value=MagicMock(user_id=user_id))
    auth.get_user_by_id = AsyncMock(return_value=MagicMock(role=Role.advertiser))
    auth.get_tariff_id_by_project_id = AsyncMock(return_value=None)
    auth.exists_orders_in_project = AsyncMock(return_value=list(order_ids or []))
    auth.get_project_order_ids = AsyncMock(return_value=list(order_ids or []))
    return auth


def test_universal_calls_create_post_custom_orders_with_project_orders() -> None:
    user_id = uuid4()
    project_id = uuid4()
    order_a = uuid4()
    order_b = uuid4()
    auth = _owner_auth(user_id=user_id, order_ids=[order_a, order_b])
    files = [MagicMock()]
    uploader = AsyncMock(return_value=files)
    create_custom = AsyncMock()
    interactor = CollectCreateorderAcceptPost(
        auth_gateway=auth,
        media_uploader=uploader,
        create_post_custom_orders=create_custom,
    )

    async def _run():
        await interactor(
            data=CollectCreateorderAcceptInput(
                user_id=user_id,
                telegram_chat_id=1,
                project_id=project_id,
                order_id=None,
                post=BotPostDraft(local_id="x", source_message_ids=[1]),
            ),
        )

    asyncio.run(_run())
    create_custom.assert_awaited_once()
    payload = create_custom.await_args.kwargs["data"]
    assert payload.project_id == project_id
    assert payload.user_id == user_id
    assert payload.orders == [order_a, order_b]
    assert payload.files == files
    assert payload.match_type == PostMatchType.universal
    auth.get_project_order_ids.assert_awaited_once_with(project_id=project_id)


def test_universal_raises_when_project_has_no_orders() -> None:
    user_id = uuid4()
    auth = _owner_auth(user_id=user_id, order_ids=[])
    create_custom = AsyncMock()
    interactor = CollectCreateorderAcceptPost(
        auth_gateway=auth,
        media_uploader=AsyncMock(return_value=[MagicMock()]),
        create_post_custom_orders=create_custom,
    )

    async def _run():
        with pytest.raises(OrderToMatchNotFound):
            await interactor(
                data=CollectCreateorderAcceptInput(
                    user_id=user_id,
                    telegram_chat_id=1,
                    project_id=uuid4(),
                    order_id=None,
                    post=BotPostDraft(local_id="x", source_message_ids=[1]),
                ),
            )

    asyncio.run(_run())
    create_custom.assert_not_awaited()


def test_unique_calls_create_post_custom_orders() -> None:
    user_id = uuid4()
    project_id = uuid4()
    order_id = uuid4()
    auth = _owner_auth(user_id=user_id, order_ids=[order_id])
    create_custom = AsyncMock()
    interactor = CollectCreateorderAcceptPost(
        auth_gateway=auth,
        media_uploader=AsyncMock(return_value=[MagicMock()]),
        create_post_custom_orders=create_custom,
    )

    async def _run():
        await interactor(
            data=CollectCreateorderAcceptInput(
                user_id=user_id,
                telegram_chat_id=1,
                project_id=project_id,
                order_id=order_id,
                post=BotPostDraft(local_id="x", source_message_ids=[1]),
            ),
        )

    asyncio.run(_run())
    create_custom.assert_awaited_once()
    payload = create_custom.await_args.kwargs["data"]
    assert payload.orders == [order_id]
    assert payload.match_type == PostMatchType.individual
    auth.get_project_order_ids.assert_not_awaited()


def test_unique_raises_when_order_not_in_project() -> None:
    user_id = uuid4()
    project_id = uuid4()
    order_id = uuid4()
    auth = _owner_auth(user_id=user_id, order_ids=[])
    create_custom = AsyncMock()
    interactor = CollectCreateorderAcceptPost(
        auth_gateway=auth,
        media_uploader=AsyncMock(return_value=[MagicMock()]),
        create_post_custom_orders=create_custom,
    )

    async def _run():
        with pytest.raises(OrderNotFound):
            await interactor(
                data=CollectCreateorderAcceptInput(
                    user_id=user_id,
                    telegram_chat_id=1,
                    project_id=project_id,
                    order_id=order_id,
                    post=BotPostDraft(local_id="x", source_message_ids=[1]),
                ),
            )

    asyncio.run(_run())
    create_custom.assert_not_awaited()
