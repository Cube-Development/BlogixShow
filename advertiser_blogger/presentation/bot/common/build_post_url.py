from aiogram.types import Message

from advertiser_blogger.presentation.bot.common.forward_message import (
    extract_telegram_url_from_body,
    get_forward_source,
    get_message_body,
)


def build_post_url(message: Message) -> str:
    source = get_forward_source(message=message)
    if source is not None and source.post_url is not None:
        return source.post_url
    body = get_message_body(message=message)
    url = extract_telegram_url_from_body(body=body)
    if url is not None:
        return url
    return message.text or ""
