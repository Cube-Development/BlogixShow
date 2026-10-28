from dataclasses import dataclass

from aiogram.types import Message

from advertiser_blogger.presentation.bot.common.forward_message import (
    build_post_url_from_channel,
    get_message_body,
    telegram_chat_id_to_channel_ident,
)


@dataclass(frozen=True)
class ChannelPostSubmission:
    channel_ident: int
    channel_username: str | None
    post_url: str
    text: str | None


def extract_channel_post_submission(message: Message) -> ChannelPostSubmission:
    channel_ident = telegram_chat_id_to_channel_ident(chat_id=message.chat.id)
    post_url = build_post_url_from_channel(chat=message.chat, message_id=message.message_id)
    text = get_message_body(message=message)
    return ChannelPostSubmission(
        channel_ident=channel_ident,
        channel_username=message.chat.username,
        post_url=post_url,
        text=text,
    )
