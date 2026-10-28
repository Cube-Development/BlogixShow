import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from advertiser_blogger.application.events.verify_post_scheduled.dto import VerifyOrderKind, VerifyOrderResult
from advertiser_blogger.application.interactors_bot.run_post_checking.dto import RunPostCheckingDtoInput
from advertiser_blogger.application.interactors_bot.run_post_checking.use_case import RunPostCheckingInteractor
from advertiser_blogger.domain.record.order.constants import OrderStatus

PROJECT_ID = uuid.uuid4()
MISSING_PROJECT_ID = uuid.uuid4()
WAIT_ORDER_ID = uuid.uuid4()
CANCELED_ORDER_ID = uuid.uuid4()


def _build_interactor(
        *,
        project_exist_map: dict[uuid.UUID, uuid.UUID | None],
        order_ids: list[uuid.UUID],
        statuses: dict[uuid.UUID, OrderStatus],
        verify_result: VerifyOrderResult | None = None,
) -> tuple[RunPostCheckingInteractor, AsyncMock, MagicMock]:
    db_gateway = MagicMock()
    db_gateway.project_exist = AsyncMock(side_effect=lambda project_id: project_exist_map.get(project_id))
    db_gateway.get_project_order_ids = AsyncMock(return_value=order_ids)
    db_gateway.get_order_status = AsyncMock(side_effect=lambda order_id: statuses.get(order_id))
    db_gateway.close = AsyncMock()

    verify_event = MagicMock()
    verify_event.verify_order_now = AsyncMock(return_value=verify_result)

    interactor = RunPostCheckingInteractor(db_gateway=db_gateway, verify_event=verify_event)
    return interactor, verify_event.verify_order_now, db_gateway


def test_run_post_checking_project_not_found() -> None:
    interactor, verify_now, db_gateway = _build_interactor(
        project_exist_map={MISSING_PROJECT_ID: None},
        order_ids=[],
        statuses={},
    )

    output = asyncio.run(interactor(data=RunPostCheckingDtoInput(project_ids=[MISSING_PROJECT_ID])))

    assert "1 projects not found" in output.header
    assert any(str(MISSING_PROJECT_ID) in line for line in output.errors)
    assert output.cards == []
    verify_now.assert_not_awaited()
    db_gateway.get_project_order_ids.assert_not_awaited()
    db_gateway.close.assert_awaited_once()


def test_run_post_checking_skips_canceled() -> None:
    interactor, verify_now, db_gateway = _build_interactor(
        project_exist_map={PROJECT_ID: PROJECT_ID},
        order_ids=[CANCELED_ORDER_ID],
        statuses={CANCELED_ORDER_ID: OrderStatus.canceled},
    )

    output = asyncio.run(interactor(data=RunPostCheckingDtoInput(project_ids=[PROJECT_ID])))

    assert "0 orders" in output.header
    assert "1 skipped" in output.header
    assert output.cards == []
    assert output.errors == []
    verify_now.assert_not_awaited()
    db_gateway.close.assert_awaited_once()


def test_run_post_checking_verifies_wait_order() -> None:
    result = VerifyOrderResult(
        kind=VerifyOrderKind.not_found,
        order_id=WAIT_ORDER_ID,
        channel_url="https://t.me/example",
    )
    interactor, verify_now, db_gateway = _build_interactor(
        project_exist_map={PROJECT_ID: PROJECT_ID},
        order_ids=[WAIT_ORDER_ID, CANCELED_ORDER_ID],
        statuses={
            WAIT_ORDER_ID: OrderStatus.wait,
            CANCELED_ORDER_ID: OrderStatus.canceled,
        },
        verify_result=result,
    )

    output = asyncio.run(interactor(data=RunPostCheckingDtoInput(project_ids=[PROJECT_ID])))

    assert "1 orders" in output.header
    assert "1 skipped" in output.header
    assert len(output.cards) == 1
    assert output.cards[0].project_id == PROJECT_ID
    assert output.cards[0].result.kind == VerifyOrderKind.not_found
    assert output.cards[0].result.order_id == WAIT_ORDER_ID
    verify_now.assert_awaited_once_with(
        order_id=WAIT_ORDER_ID,
        is_final=True,
        apply_time_gate=False,
        close=False,
        notify_outbox=False,
    )
    db_gateway.close.assert_awaited_once()
