from aiogram import Bot
import json

from advertiser_blogger.application.interactors_bot.verify_and_publish_post.dto import (
    LowSimilarity, NoOrders, VerifyAndPublishPostDtoInput,
)
from advertiser_blogger.application.interactors_bot.verify_and_publish_post.use_case import (
    VerifyAndPublishPostInteractor,
)
from advertiser_blogger.application.interactors_bot.verify_submission_processor.dto import VerifyContext
from advertiser_blogger.application.read.read_blogger_projects.use_case import ReadBloggerProjectsInteractor
from advertiser_blogger.infrastructure.cache.cache_client import RedisCacheSystem
from advertiser_blogger.presentation.bot.common.active_projects import send_active_projects_list
from advertiser_blogger.presentation.bot.common.extract_post_submission import PostSubmissionInput
from advertiser_blogger.presentation.bot.common.verify_messages import (
    ALBUM_NO_CAPTION_MESSAGE,
    NO_ORDERS_SHORT_MESSAGE,
    VERIFY_STARTED_MESSAGE,
    format_low_similarity_in_project_message,
    format_verify_result,
)
from advertiser_blogger.presentation.bot.common.verify_pending_submission import save_verify_pending_submission
from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard


class VerifySubmissionProcessor:
    def __init__(
            self,
            bot: Bot,
            interactor: VerifyAndPublishPostInteractor,
            projects_interactor: ReadBloggerProjectsInteractor,
            inline: InlineKeyboard,
            cache: RedisCacheSystem,
    ) -> None:
        self._bot = bot
        self._interactor = interactor
        self._projects_interactor = projects_interactor
        self._inline = inline
        self._cache = cache

    async def process(self, submission: PostSubmissionInput, context: VerifyContext) -> None:
        if context.message is not None:
            print(
                f"[verify.processor] "
                f"{json.dumps(context.message.model_dump(mode='python', exclude_none=True), default=str, ensure_ascii=False)}",
                flush=True,
            )
        if submission.is_album and not submission.text and not submission.post_url:
            await self._bot.send_message(chat_id=context.chat_id, text=ALBUM_NO_CAPTION_MESSAGE)
            return

        await self._bot.send_message(chat_id=context.chat_id, text=VERIFY_STARTED_MESSAGE)
        result = await self._interactor(
            data=VerifyAndPublishPostDtoInput(
                user_id=context.user.id,
                telegram_id=context.telegram_id,
                submission=submission,
            ),
        )
        if isinstance(result, (NoOrders, LowSimilarity)):
            await save_verify_pending_submission(
                cache=self._cache,
                telegram_id=context.telegram_id,
                submission=submission,
            )
            if isinstance(result, LowSimilarity):
                await self._bot.send_message(
                    chat_id=context.chat_id,
                    text=format_low_similarity_in_project_message(score=result.best_score),
                )
            elif isinstance(result, NoOrders):
                await self._bot.send_message(chat_id=context.chat_id, text=NO_ORDERS_SHORT_MESSAGE)
            if context.message is not None and context.state is not None:
                await send_active_projects_list(
                    message=context.message,
                    user=context.user,
                    inline=self._inline,
                    interactor=self._projects_interactor,
                    state=context.state,
                )
            return
        await self._bot.send_message(
            chat_id=context.chat_id,
            text=format_verify_result(result=result),
        )
