import re
from dataclasses import dataclass
from datetime import datetime

from aiogram.enums import ChatType
from aiogram.types import (
    Chat, Message, MessageOriginChannel, MessageOriginChat,
    MessageOriginHiddenUser, MessageOriginUser,
)

from advertiser_blogger.presentation.bot.album.models import AlbumPart

TELEGRAM_URL_RE = re.compile(r"https?://(?:t\.me|telegram\.me)/\S+", re.I)


@dataclass(frozen=True)
class ForwardSource:
    channel_ident: int | None
    channel_username: str | None
    message_id: int | None
    post_url: str | None


def is_any_forward(message: Message) -> bool:
    if message.forward_origin is not None:
        return True
    if message.forward_from_chat is not None:
        return True
    if message.forward_from is not None:
        return True
    return False


def telegram_chat_id_to_channel_ident(chat_id: int) -> int:
    chat_id_str = str(chat_id)
    if chat_id_str.startswith("-100"):
        return int(chat_id_str[4:])
    return abs(chat_id)


def build_post_url_from_channel(chat: Chat, message_id: int) -> str:
    if chat.username is not None:
        return f"https://t.me/{chat.username}/{message_id}"
    chat_id = str(chat.id)[4:] if str(chat.id).startswith("-100") else str(abs(chat.id))
    return f"https://t.me/c/{chat_id}/{message_id}"


def _forward_source_from_channel_chat(chat: Chat, message_id: int | None) -> ForwardSource:
    if chat.type != ChatType.CHANNEL or message_id is None:
        return ForwardSource(
            channel_ident=None,
            channel_username=None,
            message_id=message_id,
            post_url=None,
        )
    return ForwardSource(
        channel_ident=telegram_chat_id_to_channel_ident(chat.id),
        channel_username=chat.username,
        message_id=message_id,
        post_url=build_post_url_from_channel(chat=chat, message_id=message_id),
    )


def get_forward_source(message: Message) -> ForwardSource | None:
    if not is_any_forward(message):
        return None

    if message.forward_origin is not None:
        origin = message.forward_origin
        if isinstance(origin, MessageOriginChannel):
            return _forward_source_from_channel_chat(chat=origin.chat, message_id=origin.message_id)
        if isinstance(origin, MessageOriginChat):
            return ForwardSource(None, None, origin.message_id, None)
        if isinstance(origin, (MessageOriginUser, MessageOriginHiddenUser)):
            if message.forward_from_chat is not None:
                return _forward_source_from_channel_chat(
                    chat=message.forward_from_chat,
                    message_id=message.forward_from_message_id,
                )
            return ForwardSource(None, None, None, None)

    if message.forward_from_chat is not None:
        return _forward_source_from_channel_chat(
            chat=message.forward_from_chat,
            message_id=message.forward_from_message_id,
        )

    return ForwardSource(None, None, None, None)


def get_message_body(message: Message) -> str | None:
    return message.text or message.caption


def extract_telegram_url_from_body(body: str | None) -> str | None:
    if not body:
        return None
    match = TELEGRAM_URL_RE.search(body)
    if match is None:
        return None
    return match.group(0)


def get_forward_part_metadata(
        message: Message,
) -> tuple[bool, int | None, str | None, int | None, datetime | None]:
    if message.forward_origin is not None:
        origin = message.forward_origin
        if isinstance(origin, MessageOriginChannel):
            return (
                True,
                origin.chat.id,
                origin.chat.username,
                origin.message_id,
                origin.date,
            )

    if message.forward_from_chat is not None and message.forward_from_chat.type == ChatType.CHANNEL:
        return (
            True,
            message.forward_from_chat.id,
            message.forward_from_chat.username,
            message.forward_from_message_id,
            message.forward_date,
        )

    return False, None, None, None, None


def get_forward_source_from_album_part(part: AlbumPart) -> ForwardSource | None:
    if not part.is_forward or part.forward_chat_id is None or part.forward_message_id is None:
        return None
    return _forward_source_from_channel_chat(
        chat=Chat(
            id=part.forward_chat_id,
            type=ChatType.CHANNEL,
            username=part.forward_chat_username,
        ),
        message_id=part.forward_message_id,
    )
