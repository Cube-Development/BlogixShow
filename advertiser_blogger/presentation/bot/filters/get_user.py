from typing import Optional, Any

from aiogram.filters import Filter
from aiogram.types import TelegramObject, User
from dishka import FromDishka
from dishka.integrations.aiogram import inject

from advertiser_blogger.infrastructure.db.repositories.bot_repository import BotRepository


class GetUserByTelegramId(Filter):
    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name

    @inject
    async def __call__(
            self,
            event: TelegramObject,
            event_from_user: User,
            bot_repo: FromDishka[BotRepository],
    ) -> bool | dict[str, Any]:
        if event_from_user is None:
            return False
        user = await bot_repo.get_user_by_telegram_id(telegram_id=event_from_user.id)
        if user is None:
            return False
        return {"user": user}
