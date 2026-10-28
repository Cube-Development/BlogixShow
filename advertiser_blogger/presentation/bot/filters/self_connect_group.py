from aiogram.filters import Filter
from aiogram.types import Message
from dishka import FromDishka
from dishka.integrations.aiogram import inject

from configuration.common import CommonConfig
from configuration.secret import GroupTopic

SCREENSHOT_TOPIC = "Screenshot"


def _topic_id(topics: list[GroupTopic], name: str) -> int | None:
    for topic in topics:
        if topic.name == name:
            return topic.topic_id
    return None


class IsSelfConnectGroup(Filter):
    @inject
    async def __call__(
            self,
            message: Message,
            config: FromDishka[CommonConfig],
    ) -> bool:
        return message.chat.id == config.bot.self_connect_group_chat_id


class IsScreenshotTopic(Filter):
    @inject
    async def __call__(
            self,
            message: Message,
            config: FromDishka[CommonConfig],
    ) -> bool:
        topic_id = _topic_id(config.bot.topics, SCREENSHOT_TOPIC)
        print((
            message.chat.id, config.bot.events_group_chat_id,
            message.message_thread_id, topic_id
        ))
        if topic_id is None:
            return False
        return (
            message.chat.id == config.bot.events_group_chat_id
            and message.message_thread_id == topic_id
        )
