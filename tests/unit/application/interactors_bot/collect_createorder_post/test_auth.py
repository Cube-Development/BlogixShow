from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from advertiser_blogger.application.common.exceptions.application_error import (
    AccessDenied,
    ManagerNotFound,
    OrderNotFound,
    ProjectNotFound,
)
from advertiser_blogger.application.interactors_bot.collect_createorder_post.auth import (
    assert_collect_createorder_access,
)
from advertiser_blogger.domain.read.constants import Role


def _gateway(**kwargs):
    gw = MagicMock()
    for key, val in kwargs.items():
        setattr(gw, key, AsyncMock(return_value=val))
    gw.close = AsyncMock()
    return gw


def test_raises_when_project_missing() -> None:
    async def _run():
        with pytest.raises(ProjectNotFound):
            await assert_collect_createorder_access(
                _gateway(get_project=None),
                user_id=uuid4(),
                project_id=uuid4(),
                order_id=None,
            )

    asyncio.run(_run())


def test_raises_when_not_project_owner() -> None:
    user_id = uuid4()
    project_id = uuid4()

    async def _run():
        with pytest.raises(AccessDenied):
            await assert_collect_createorder_access(
                _gateway(
                    get_project=MagicMock(user_id=uuid4()),
                    get_user_by_id=MagicMock(role=Role.advertiser),
                    get_tariff_id_by_project_id=None,
                ),
                user_id=user_id,
                project_id=project_id,
                order_id=None,
            )

    asyncio.run(_run())


def test_raises_when_order_not_in_project() -> None:
    user_id = uuid4()
    project_id = uuid4()
    order_id = uuid4()

    async def _run():
        with pytest.raises(OrderNotFound):
            await assert_collect_createorder_access(
                _gateway(
                    get_project=MagicMock(user_id=user_id),
                    get_user_by_id=MagicMock(role=Role.advertiser),
                    get_tariff_id_by_project_id=None,
                    exists_orders_in_project=[],
                ),
                user_id=user_id,
                project_id=project_id,
                order_id=order_id,
            )

    asyncio.run(_run())


def test_allows_owner_universal() -> None:
    user_id = uuid4()
    project_id = uuid4()

    async def _run():
        await assert_collect_createorder_access(
            _gateway(
                get_project=MagicMock(user_id=user_id),
                get_user_by_id=MagicMock(role=Role.advertiser),
                get_tariff_id_by_project_id=None,
            ),
            user_id=user_id,
            project_id=project_id,
            order_id=None,
        )

    asyncio.run(_run())


def test_raises_when_owner_missing() -> None:
    async def _run():
        with pytest.raises(ManagerNotFound):
            await assert_collect_createorder_access(
                _gateway(
                    get_project=MagicMock(user_id=uuid4()),
                    get_user_by_id=None,
                    get_tariff_id_by_project_id=None,
                ),
                user_id=uuid4(),
                project_id=uuid4(),
                order_id=None,
            )

    asyncio.run(_run())


def test_allows_manager_on_tariff_project() -> None:
    user_id = uuid4()
    project_id = uuid4()

    async def _run():
        await assert_collect_createorder_access(
            _gateway(
                get_project=MagicMock(user_id=uuid4()),
                get_user_by_id=MagicMock(role=Role.manager),
                get_tariff_id_by_project_id=uuid4(),
            ),
            user_id=user_id,
            project_id=project_id,
            order_id=None,
        )

    asyncio.run(_run())


def test_raises_when_advertiser_on_tariff_project() -> None:
    user_id = uuid4()
    project_id = uuid4()

    async def _run():
        with pytest.raises(AccessDenied):
            await assert_collect_createorder_access(
                _gateway(
                    get_project=MagicMock(user_id=user_id),
                    get_user_by_id=MagicMock(role=Role.advertiser),
                    get_tariff_id_by_project_id=uuid4(),
                ),
                user_id=user_id,
                project_id=project_id,
                order_id=None,
            )

    asyncio.run(_run())


def test_allows_owner_unique_when_order_in_project() -> None:
    user_id = uuid4()
    project_id = uuid4()
    order_id = uuid4()

    async def _run():
        await assert_collect_createorder_access(
            _gateway(
                get_project=MagicMock(user_id=user_id),
                get_user_by_id=MagicMock(role=Role.advertiser),
                get_tariff_id_by_project_id=None,
                exists_orders_in_project=[order_id],
            ),
            user_id=user_id,
            project_id=project_id,
            order_id=order_id,
        )

    asyncio.run(_run())
