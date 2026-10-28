from typing import Optional
from structlog import get_logger
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
import asyncio
import json
from uuid import UUID, uuid4
from urllib.parse import urlparse, urlunparse

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.deep_linking import create_start_link

from advertiser_blogger.application.common.cache.models import InsertRedisData
from advertiser_blogger.domain.record.order.constants import DeeplinkType, Subrole
from advertiser_blogger.domain.record.order.entities.deeplink import Deeplink
from advertiser_blogger.infrastructure.cache.cache_client import RedisCacheSystem

logger = get_logger(__name__)

def convert_tg_link(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc == "t.me":
        parsed = parsed._replace(netloc="telegram.me")
    return urlunparse(parsed)


class TelegramBotService:
    def __init__(self, bot: Bot, cache_gateway: RedisCacheSystem):
        self.bot = bot
        self.cache_gateway = cache_gateway

    async def save_deeplink(self, type: DeeplinkType, payload: dict) -> UUID:
        deeplink = Deeplink(
            id=uuid4(), type=type, payload=payload,
        )
        value = json.dumps(deeplink.__dict__, separators=(",", ":"), default=str)
        await self.cache_gateway.set(
            payload=InsertRedisData(
                name=str(deeplink.id), user_id="", value=value,
                expires=86400,
            )
        )
        return deeplink.id

    async def create_post_link(self, type: DeeplinkType, order_id: UUID) -> str:
        deeplink_id = await self.save_deeplink(type=type, payload={"order_id": order_id})
        link = await create_start_link(
            bot=self.bot, payload=str(deeplink_id), encode=True,
        )
        return convert_tg_link(link)

    async def create_attach_user_link(self, type: DeeplinkType, attach_id: UUID) -> str:
        deeplink_id = await self.save_deeplink(type=type, payload={"attach_id": attach_id})
        link = await create_start_link(
            bot=self.bot, payload=str(deeplink_id), encode=True,
        )
        return convert_tg_link(link)

    async def create_attach_actor_link(
            self, type: DeeplinkType, project_id: UUID, subrole: Subrole,
    ) -> str:
        deeplink_id = await self.save_deeplink(type=type, payload={"project_id": project_id, "subrole": subrole})
        link = await create_start_link(
            bot=self.bot, payload=str(deeplink_id), encode=True,
        )
        return convert_tg_link(link)
    
    async def send_message(
            self, chat_id: int, text: str, message_thread_id: int | None = None,
            reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message:
        try:
            message = await self.bot.send_message(
                chat_id=chat_id, text=text, message_thread_id=message_thread_id,
                reply_markup=reply_markup,
            )
            return message
        except TelegramForbiddenError as ex:
            logger.warning("telegram send message forbidden", chat_id=chat_id, error=str(ex))
        except Exception:
            logger.exception("telegram send message failed", chat_id=chat_id, thread_id=message_thread_id)

    async def send_photo(
            self, chat_id: int, photo: str, caption: Optional[str] = None,
            message_thread_id: int | None = None,
    ) -> None:
        try:
            await self.bot.send_photo(
                chat_id=chat_id, photo=photo, caption=caption, message_thread_id=message_thread_id,
            )
        except Exception:
            logger.exception("telegram send photo failed", chat_id=chat_id, thread_id=message_thread_id)
    
    async def unpin_message(self, chat_id: int, message_id: int) -> None:
        try:
            await self.bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            logger.exception("telegram unpin message failed", chat_id=chat_id, message_id=message_id)
    
    async def delete_message(self, chat_id: int, message_id: int) -> None:
        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            logger.exception("telegram delete message failed", chat_id=chat_id, message_id=message_id)
    
    async def pin_message(self, chat_id: int, message_id: int) -> None:
        try:
            await self.bot.pin_chat_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            logger.exception("telegram pin message failed", chat_id=chat_id, message_id=message_id)
    
    async def edit_message_text(self, chat_id: int, message_id: int, text: str) -> Message:
        try:
            message = await self.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
            return message
        except TelegramBadRequest as ex:
            logger.warning("telegram edit message rejected", chat_id=chat_id, message_id=message_id, error=str(ex))
        except Exception:
            logger.exception("telegram edit message failed", chat_id=chat_id, message_id=message_id)
