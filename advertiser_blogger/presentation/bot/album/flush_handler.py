from structlog import get_logger

from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Message
from dishka import AsyncContainer

from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import ResolveChannelQueries
from advertiser_blogger.application.interactors_bot.verify_submission_processor.dto import VerifyContext
from advertiser_blogger.application.interactors_bot.verify_submission_processor.use_case import (
    VerifySubmissionProcessor,
)
from advertiser_blogger.infrastructure.db.repositories.bot_repository import BotRepository
from advertiser_blogger.presentation.bot.album.models import AggregatedAlbum
from advertiser_blogger.presentation.bot.common.extract_post_submission import extract_post_submission_from_album
from advertiser_blogger.presentation.bot.common.project_create_draft import (
    load_draft,
    pop_pending_by_reply_to_ids,
    pop_pending_metadata,
    project_create_user_lock,
)
from advertiser_blogger.presentation.bot.handlers.user.project_create import (
    _apply_metadata_and_show_preview,
    finalize_album_ingest_in_project_create,
    ingest_album_into_draft,
    replace_post_from_album_in_project_create,
)
from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard
from advertiser_blogger.presentation.bot.filters.collect_createorder import is_collect_createorder_state
from advertiser_blogger.presentation.bot.handlers.user.collect_createorder import collect_receive_album
from advertiser_blogger.presentation.bot.states.project_create import ProjectCreateState
from configuration.common import CommonConfig

logger = get_logger(__name__)

_container: AsyncContainer | None = None


def bind_album_flush_container(container: AsyncContainer) -> None:
    global _container
    _container = container


async def handle_album_flush(aggregated: AggregatedAlbum, message: Message) -> bool:
    if _container is None:
        raise RuntimeError("Album flush container is not bound")

    if message.from_user is None:
        logger.warning("album flush skipped: message has no from_user")
        return False

    async with _container() as request_container:
        bot = await request_container.get(Bot)
        dp = await request_container.get(Dispatcher)
        bot_repo = await request_container.get(BotRepository)

        user = await bot_repo.get_user_by_telegram_id(telegram_id=message.from_user.id)
        if user is None:
            logger.warning("album flush skipped: user not found", telegram_id=message.from_user.id)
            return False

        storage_key = StorageKey(
            bot_id=bot.id,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
        )
        fsm = FSMContext(storage=dp.storage, key=storage_key)
        current_state = await fsm.get_state()
        inline = await request_container.get(InlineKeyboard)
        if is_collect_createorder_state(current_state):
            async with project_create_user_lock(message.from_user.id):
                if await collect_receive_album(
                    state=fsm,
                    message=message,
                    bot=bot,
                    inline=inline,
                    aggregated=aggregated,
                ):
                    return True
        if (
            current_state
            and str(current_state).startswith("ProjectCreateState")
            and "choosing_publish_mode" not in str(current_state)
        ):
            async with project_create_user_lock(message.from_user.id):
                if await replace_post_from_album_in_project_create(
                    state=fsm,
                    user=user,
                    aggregated=aggregated,
                    message=message,
                    bot=bot,
                    inline=await request_container.get(InlineKeyboard),
                ):
                    return True
                new_post = await ingest_album_into_draft(
                    state=fsm, user=user, aggregated=aggregated, message=message,
                )
                draft = await load_draft(fsm)
                message_ids = [p.message_id for p in aggregated.parts]
                pending_by_reply = await pop_pending_by_reply_to_ids(fsm, message_ids)
                resolve_channels = await request_container.get(ResolveChannelQueries)
                config = await request_container.get(CommonConfig)
                inline = await request_container.get(InlineKeyboard)
                if pending_by_reply and draft is not None:
                    for reply_mid, pending_text in pending_by_reply:
                        await _apply_metadata_and_show_preview(
                            message=message,
                            state=fsm,
                            user=user,
                            draft=draft,
                            resolve_channels=resolve_channels,
                            config=config,
                            inline=inline,
                            bot=bot,
                            metadata_text=pending_text,
                            reply_to_message_id=reply_mid,
                            show_preview=False,
                        )
                        draft = await load_draft(fsm) or draft
                from advertiser_blogger.presentation.bot.common.project_create_draft import (
                    has_post_waiting_for_channels,
                    peek_pending_metadata,
                )
                draft = await load_draft(fsm) or draft
                while (
                    draft is not None
                    and has_post_waiting_for_channels(draft)
                    and await peek_pending_metadata(fsm)
                ):
                    pending = await pop_pending_metadata(fsm)
                    if not pending:
                        break
                    await _apply_metadata_and_show_preview(
                        message=message,
                        state=fsm,
                        user=user,
                        draft=draft,
                        resolve_channels=resolve_channels,
                        config=config,
                        inline=inline,
                        bot=bot,
                        metadata_text=pending,
                        show_preview=False,
                    )
                    draft = await load_draft(fsm) or draft
                await finalize_album_ingest_in_project_create(
                    message=message,
                    state=fsm,
                    user=user,
                    bot=bot,
                    config=config,
                    inline=inline,
                    resolve_channels=resolve_channels,
                    newly_created_post=new_post,
                )
            return True

        processor = await request_container.get(VerifySubmissionProcessor)
        submission = extract_post_submission_from_album(
            aggregated=aggregated,
            source_message=message,
        )

        context = VerifyContext(
            user=user,
            telegram_id=message.from_user.id,
            chat_id=message.chat.id,
            message=message,
            state=None,
        )
        await processor.process(submission=submission, context=context)
        return True
