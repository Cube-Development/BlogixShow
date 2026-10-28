"""
Legacy polling entrypoint for local debugging only.

The bot runs in webhook mode via the FastAPI app
(advertiser_blogger.presentation.web.build_app.build_web).
Do not run this script together with the web app on the same bot token.
"""
import asyncio
from structlog import get_logger

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka

from advertiser_blogger.infrastructure.di.providers.authentication import AuthenticationProvider
from advertiser_blogger.infrastructure.di.providers.config_provider import ConfigProvider
from advertiser_blogger.infrastructure.di.providers.domain_services import DomainServiceProvider
from advertiser_blogger.infrastructure.di.providers.event_provider import EventProvider
from advertiser_blogger.infrastructure.di.providers.infrastructure_provider import InfrastructureProvider
from advertiser_blogger.infrastructure.di.providers.bot_interactor import BotInteractorProvider
from advertiser_blogger.infrastructure.di.providers.read_interactor import ReadProvider
from advertiser_blogger.infrastructure.di.providers.record_interactor import CommandProvider
from advertiser_blogger.infrastructure.di.providers.telegram_bot import TelegramBotProvider
from advertiser_blogger.presentation.bot.album.flush_handler import bind_album_flush_container
from advertiser_blogger.presentation.bot.message_batch.flush_handler import (
    bind_message_batch_flush_container,
)
from advertiser_blogger.presentation.bot.handlers import main_router
from configuration.logging import setup_logging

logger = get_logger(__name__)


async def main() -> None:
    container = make_async_container(
        ReadProvider(), CommandProvider(), BotInteractorProvider(), AuthenticationProvider(),
        DomainServiceProvider(), ConfigProvider(), InfrastructureProvider(), EventProvider(),
        TelegramBotProvider(),
    )
    bind_album_flush_container(container)
    bind_message_batch_flush_container(container)
    dp = await container.get(Dispatcher)
    bot = await container.get(Bot)
    setup_dishka(container=container, router=dp, auto_inject=True)
    await bot.set_my_commands(
        commands=[
            BotCommand(
                command="start",
                description="tap to start",
            ),
        ],
    )
    dp.include_routers(*main_router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Telegram webhook removed before polling")
    logger.info("Bot started in polling mode (local debug only)")
    await dp.start_polling(bot)


if __name__ == '__main__':
    setup_logging()
    asyncio.run(main())
