from datetime import datetime, timedelta
from structlog import get_logger

from advertiser_blogger.application.common.constants import Timezone
from advertiser_blogger.application.common.use_case import UseCase
from advertiser_blogger.application.interactors_bot.match_and_attach_post.dto import (
    MatchAlreadyPublished, MatchAndAttachPostDtoInput, MatchAndAttachPostResult,
    MatchLowSimilarity, MatchNoOrders, MatchPublishFailed, MatchSuccess,
)
from advertiser_blogger.application.interactors_bot.match_and_attach_post.interface import (
    PostTextProviderGateway, ReadDbGateway, RecordDbGateway,
)
from advertiser_blogger.application.interactors_bot.publish_post_broadcast.dto import (
    PublishObject, PublishPostBroadcastDtoInput,
)
from advertiser_blogger.application.interactors_bot.publish_post_broadcast.use_case import (
    PublishPostBroadcastInteractor,
)
from advertiser_blogger.domain.common.post_text_matcher import PostTextMatcher
from advertiser_blogger.domain.record.order.constants import OrderStatus

logger = get_logger(__name__)


class MatchAndAttachPostInteractor(UseCase[MatchAndAttachPostDtoInput, MatchAndAttachPostResult]):
    def __init__(
            self,
            read_gateway: ReadDbGateway,
            record_gateway: RecordDbGateway,
            publish_interactor: PublishPostBroadcastInteractor,
            post_text_provider: PostTextProviderGateway,
    ):
        self.read_gateway = read_gateway
        self.record_gateway = record_gateway
        self.publish_interactor = publish_interactor
        self.matcher = PostTextMatcher(post_text_provider=post_text_provider)

    async def __call__(self, data: MatchAndAttachPostDtoInput) -> MatchAndAttachPostResult:
        if data.order_id is not None:
            published = await self.record_gateway.is_exist_post(order_id=data.order_id)
            if published is not None:
                return MatchAlreadyPublished(order_id=data.order_id)

        candidates = await self._load_candidates(data=data)
        await self.read_gateway.close()

        if not candidates:
            logger.info(
                "match and attach: no candidates",
                source=data.source, order_id=data.order_id, channel_ident=data.channel_ident,
            )
            return MatchNoOrders()

        best_candidate, best_breakdown = await self.matcher.find_best_candidate(
            candidates=candidates,
            submitted_text=data.submitted_text,
        )
        if best_breakdown is None or not best_breakdown.is_match:
            logger.info(
                "match and attach: low similarity",
                source=data.source,
                order_id=best_candidate.order_id if best_candidate else None,
                token_set=best_breakdown.display_score if best_breakdown else 0.0,
                ratio=best_breakdown.ratio if best_breakdown else 0.0,
                reason=best_breakdown.reason if best_breakdown else "empty_text",
            )
            return MatchLowSimilarity(
                best_score=best_breakdown.display_score if best_breakdown else 0.0,
                order_id=best_candidate.order_id if best_candidate else None,
            )

        best_score = best_breakdown.display_score
        publish_result = await self.publish_interactor(
            data=PublishPostBroadcastDtoInput(
                user_id=data.user_id,
                telegram_id=data.telegram_id,
                posts=[
                    PublishObject(
                        order_id=best_candidate.order_id,
                        post_url=data.post_url,
                    ),
                ],
            ),
        )
        result = publish_result.results[0]
        if result.success:
            logger.info(
                "match and attach: success", source=data.source, order_id=best_candidate.order_id,
                token_set=best_score, ratio=best_breakdown.ratio, reason=best_breakdown.reason,
            )
            return MatchSuccess(order_id=best_candidate.order_id, score=best_score)

        logger.warning(
            "match and attach: publish failed", source=data.source,
            order_id=best_candidate.order_id, reason=result.reason,
        )
        return MatchPublishFailed(
            order_id=best_candidate.order_id,
            score=best_score,
            reason=result.reason,
        )

    async def _load_candidates(self, data: MatchAndAttachPostDtoInput):
        current_datetime = datetime.utcnow() + timedelta(hours=Timezone.TASHKENT)
        order_status = [OrderStatus.wait, OrderStatus.in_progress]
        if data.order_id is not None:
            candidate = await self.read_gateway.read_order_candidate_by_order_id(
                order_id=data.order_id,
                current_datetime=current_datetime,
                order_status=order_status,
            )
            return [candidate] if candidate is not None else []
        if data.project_id is not None:
            return await self.read_gateway.read_today_order_candidates_by_project(
                executor_id=data.user_id,
                project_id=data.project_id,
                current_datetime=current_datetime,
                order_status=order_status,
                channel_ident=data.channel_ident,
            )
        if data.channel_ident is not None:
            return await self.read_gateway.read_today_order_candidates_by_channel(
                executor_id=data.user_id,
                channel_ident=data.channel_ident,
                current_datetime=current_datetime,
                order_status=order_status,
            )
        return []
