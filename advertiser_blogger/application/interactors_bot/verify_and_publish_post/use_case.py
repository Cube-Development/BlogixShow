from advertiser_blogger.application.common.use_case import UseCase
from advertiser_blogger.application.interactors_bot.match_and_attach_post.dto import (
    MatchAlreadyPublished, MatchAndAttachPostDtoInput, MatchLowSimilarity,
    MatchNoOrders, MatchPublishFailed, MatchSuccess,
)
from advertiser_blogger.application.interactors_bot.match_and_attach_post.use_case import (
    MatchAndAttachPostInteractor,
)
from advertiser_blogger.application.interactors_bot.verify_and_publish_post.dto import (
    LowSimilarity, NoOrders, PublishFailed, Success, TextUnavailable,
    VerifyAndPublishPostDtoInput, VerifyResult,
)
from advertiser_blogger.application.interactors_bot.verify_and_publish_post.interface import (
    PostTextProvider, VerifyReadGateway,
)
from advertiser_blogger.domain.common.telegram_post_url import is_telegram_post_url_only


class VerifyAndPublishPostInteractor(UseCase[VerifyAndPublishPostDtoInput, VerifyResult]):
    def __init__(
            self,
            db_gateway: VerifyReadGateway,
            match_interactor: MatchAndAttachPostInteractor,
            post_text_provider: PostTextProvider,
    ):
        self.db_gateway = db_gateway
        self.match_interactor = match_interactor
        self.post_text_provider = post_text_provider

    async def __call__(self, data: VerifyAndPublishPostDtoInput) -> VerifyResult:
        submission = data.submission
        channel_ident = await self._resolve_channel_ident(submission=submission)
        if channel_ident is None and data.project_id is None:
            await self.db_gateway.close()
            return NoOrders()

        submitted_text, _ = await self._resolve_submitted_text(submission=submission)
        if submitted_text is None:
            await self.db_gateway.close()
            return TextUnavailable(post_url=submission.post_url)

        await self.db_gateway.close()
        match_result = await self.match_interactor(
            data=MatchAndAttachPostDtoInput(
                source="blogger_submission",
                user_id=data.user_id,
                telegram_id=data.telegram_id,
                post_url=submission.post_url,
                submitted_text=submitted_text,
                channel_ident=channel_ident,
                project_id=data.project_id,
            ),
        )
        return self._map_match_result(match_result=match_result, post_url=submission.post_url)

    async def _resolve_channel_ident(self, submission) -> int | None:
        if submission.channel_ident is not None:
            return await self.db_gateway.resolve_channel_ident_in_db(channel_ident=submission.channel_ident)
        if submission.channel_username is not None:
            return await self.db_gateway.get_channel_ident_by_username(username=submission.channel_username)
        return None

    async def _resolve_submitted_text(self, submission) -> tuple[str | None, str]:
        if submission.text and not is_telegram_post_url_only(submission.text):
            return submission.text, "forward_text"
        if submission.text and is_telegram_post_url_only(submission.text):
            text = await self.post_text_provider.fetch_text(post_url=submission.post_url)
            return text, "forward_url_fetch"
        text = await self.post_text_provider.fetch_text(post_url=submission.post_url)
        return text, "link_fetch"

    @staticmethod
    def _map_match_result(match_result, post_url: str) -> VerifyResult:
        match match_result:
            case MatchSuccess(order_id=order_id, score=score):
                return Success(order_id=order_id, score=score)
            case MatchLowSimilarity(best_score=score, order_id=order_id):
                return LowSimilarity(best_score=score, order_id=order_id)
            case MatchNoOrders():
                return NoOrders()
            case MatchPublishFailed(order_id=order_id, score=score, reason=reason):
                return PublishFailed(order_id=order_id, score=score, reason=reason)
            case MatchAlreadyPublished():
                return NoOrders()
            case _:
                return NoOrders()
