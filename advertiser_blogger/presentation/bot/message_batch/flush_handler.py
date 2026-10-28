from __future__ import annotations

from structlog import get_logger

from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from dishka import AsyncContainer

from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import (
    ResolveChannelQueries,
)
from advertiser_blogger.infrastructure.db.repositories.bot_repository import BotRepository
from advertiser_blogger.presentation.bot.common.project_create_draft import project_create_user_lock
from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard
from advertiser_blogger.presentation.bot.message_batch.batch_processor import (
    process_project_create_message_batch,
)
from advertiser_blogger.presentation.bot.message_batch.models import MessageBatch
from configuration.common import CommonConfig

logger = get_logger(__name__)

_container: AsyncContainer | None = None


def bind_message_batch_flush_container(container: AsyncContainer) -> None:
    global _container
    _container = container


async def handle_message_batch_flush(batch: MessageBatch) -> bool:
    if _container is None:
        raise RuntimeError("Message batch flush container is not bound")
    if not batch.messages:
        return True

    first = batch.messages[0]
    if first.from_user is None:
        logger.warning("message batch flush skipped: no from_user")
        return False

    async with _container() as request_container:
        bot = await request_container.get(Bot)
        dp = await request_container.get(Dispatcher)
        bot_repo = await request_container.get(BotRepository)
        user = await bot_repo.get_user_by_telegram_id(telegram_id=first.from_user.id)
        if user is None:
            logger.warning("message batch flush skipped: user not found", telegram_id=first.from_user.id)
            return False

        storage_key = StorageKey(
            bot_id=bot.id,
            chat_id=batch.chat_id,
            user_id=first.from_user.id,
        )
        fsm = FSMContext(storage=dp.storage, key=storage_key)
        resolve_channels = await request_container.get(ResolveChannelQueries)
        config = await request_container.get(CommonConfig)
        inline = await request_container.get(InlineKeyboard)

        async with project_create_user_lock(first.from_user.id):
            await process_project_create_message_batch(
                batch=batch,
                state=fsm,
                user=user,
                resolve_channels=resolve_channels,
                config=config,
                inline=inline,
                bot=bot,
            )
        return True
