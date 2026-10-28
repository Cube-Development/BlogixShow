from asyncio import sleep
from structlog import get_logger

from advertiser_blogger.application.common.use_case import UseCase
from advertiser_blogger.application.events.verify_post_scheduled.dto import VerifyOrderKind
from advertiser_blogger.application.events.verify_post_scheduled.use_case import VerifyPostScheduledEvent
from advertiser_blogger.application.interactors_bot.run_post_checking.dto import (
    PostCheckingCard,
    RunPostCheckingDtoInput,
    RunPostCheckingDtoOutput,
)
from advertiser_blogger.application.interactors_bot.run_post_checking.interface import DbGateway
from advertiser_blogger.domain.record.order.constants import OrderStatus

logger = get_logger(__name__)

CHECKABLE_STATUSES = frozenset({
    OrderStatus.wait,
    OrderStatus.in_progress,
    OrderStatus.post_review,
})

TOPIC_KINDS = frozenset({
    VerifyOrderKind.ok,
    VerifyOrderKind.mismatch,
    VerifyOrderKind.not_found,
})


class RunPostCheckingInteractor(UseCase[RunPostCheckingDtoInput, RunPostCheckingDtoOutput]):
    def __init__(self, db_gateway: DbGateway, verify_event: VerifyPostScheduledEvent):
        self.db_gateway = db_gateway
        self.verify_event = verify_event

    async def __call__(self, data: RunPostCheckingDtoInput) -> RunPostCheckingDtoOutput:
        errors: list[str] = []
        cards: list[PostCheckingCard] = []
        checked = 0
        skipped = 0
        missing_projects = 0
        try:
            for project_id in data.project_ids:
                exists = await self.db_gateway.project_exist(project_id=project_id)
                if exists is None:
                    missing_projects += 1
                    errors.append(f"❌ {project_id} | project not found")
                    continue
                order_ids = await self.db_gateway.get_project_order_ids(project_id=project_id)
                for order_id in order_ids:
                    status = await self.db_gateway.get_order_status(order_id=order_id)
                    if status not in CHECKABLE_STATUSES:
                        skipped += 1
                        continue
                    try:
                        result = await self.verify_event.verify_order_now(
                            order_id=order_id,
                            is_final=True,
                            apply_time_gate=False,
                            close=False,
                            notify_outbox=False,
                        )
                    except Exception:
                        logger.exception("run post checking failed", project_id=project_id, order_id=order_id)
                        errors.append(f"❌ {project_id} | order {order_id} error")
                        continue
                    checked += 1
                    if result.kind in TOPIC_KINDS:
                        cards.append(PostCheckingCard(project_id=project_id, result=result))
                    await sleep(0.05)
        finally:
            await self.db_gateway.close()

        header = (
            f"Post checking: {len(data.project_ids)} projects, "
            f"{checked} orders, {skipped} skipped, "
            f"{missing_projects} projects not found"
        )
        return RunPostCheckingDtoOutput(header=header, errors=errors, cards=cards)
