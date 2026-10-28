from typing import Optional, Any

from aiogram.filters import Filter
from aiogram.types import Message, User
from dishka import FromDishka
from dishka.integrations.aiogram import inject

from advertiser_blogger.infrastructure.db.repositories.bot_repository import BotRepository


class GetManagerIdByPublisherFilter(Filter):
    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name

    @inject
    async def __call__(
            self,
            message: Message,
            event_from_user: User,
            bot_repo: FromDishka[BotRepository],
    ) -> bool | dict[str, Any]:
        user_id = await bot_repo.get_manager_id_by_publisher_telegram_id(telegram_id=message.from_user.id)
        if user_id is None:
            return False
        return {"user_id": user_id}


class GetProjectOwnerByBlogger(Filter):
    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name

    @inject
    async def __call__(
            self,
            message: Message,
            event_from_user: User,
            bot_repo: FromDishka[BotRepository],
    ) -> bool | dict[str, Any]:
        user_id = await bot_repo.get_manager_id_by_publisher_telegram_id(telegram_id=message.from_user.id)
        if user_id is None:
            return False
        return {"user_id": user_id}