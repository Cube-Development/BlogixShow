from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Chat, InputMediaDocument, InputMediaPhoto, InputMediaVideo

from advertiser_blogger.application.interactors_bot.project_create.models import BotPostDraft, PublishMode, resolve_publish_mode
from advertiser_blogger.presentation.bot.common.forward_message import build_post_url_from_channel


class TzPublishError(Exception):
    pass


T = TypeVar("T")
_FLOOD_RETRY_ATTEMPTS = 8


async def _call_with_flood_retry(operation: Callable[[], Awaitable[T]]) -> T:
    last_retry: TelegramRetryAfter | None = None
    for _ in range(_FLOOD_RETRY_ATTEMPTS):
        try:
            return await operation()
        except TelegramRetryAfter as exc:
            last_retry = exc
            delay = float(getattr(exc, "retry_after", 1) or 1)
            await asyncio.sleep(delay + 0.1)
    raise TzPublishError(f"flood retry exhausted: {last_retry}") from last_retry


@dataclass(frozen=True)
class PublishedToTzChannel:
    message_id: int
    chat: Chat | None = None


def format_tz_html(post_url: str) -> str:
    return f"<p>{post_url}</p>"


async def resolve_published_post_url(
        bot: Bot,
        *,
        channel_id: int,
        message_id: int,
        chat: Chat | None = None,
) -> str:
    resolved_chat = chat
    if resolved_chat is None or resolved_chat.username is None:
        try:
            resolved_chat = await bot.get_chat(channel_id)
        except Exception:
            if resolved_chat is None:
                resolved_chat = Chat(id=channel_id, type=ChatType.CHANNEL)
    return build_post_url_from_channel(chat=resolved_chat, message_id=message_id)


async def publish_draft_post_to_channel(
        bot: Bot,
        *,
        tz_channel_id: int,
        user_chat_id: int,
        post: BotPostDraft,
        publish_mode: PublishMode | None = None,
) -> PublishedToTzChannel:
    """Publish post to TZ: copy (editable) or forward bot mirror / user source."""
    mode = resolve_publish_mode(publish_mode)
    if mode is PublishMode.copy:
        if post.source_message_ids:
            try:
                return await _copy_source_messages(
                    bot=bot,
                    tz_channel_id=tz_channel_id,
                    from_chat_id=user_chat_id,
                    message_ids=post.source_message_ids,
                )
            except TzPublishError:
                pass
        return await _send_composed_post(bot=bot, tz_channel_id=tz_channel_id, post=post)
    if post.bot_message_ids:
        try:
            return await _forward_messages(
                bot=bot,
                tz_channel_id=tz_channel_id,
                from_chat_id=user_chat_id,
                message_ids=post.bot_message_ids,
            )
        except TzPublishError:
            pass
    if post.source_message_ids:
        try:
            return await _forward_messages(
                bot=bot,
                tz_channel_id=tz_channel_id,
                from_chat_id=user_chat_id,
                message_ids=post.source_message_ids,
            )
        except TzPublishError:
            pass
    return await _send_composed_post(bot=bot, tz_channel_id=tz_channel_id, post=post)


async def _copy_source_messages(
        bot: Bot,
        *,
        tz_channel_id: int,
        from_chat_id: int,
        message_ids: list[int],
) -> PublishedToTzChannel:
    """Copy (not forward) so the TZ channel shows a clean editable post."""
    try:
        ids = sorted(set(message_ids))
        if not ids:
            raise TzPublishError("no source message ids to copy")
        if len(ids) == 1:
            sent = await _call_with_flood_retry(
                lambda: bot.copy_message(
                    chat_id=tz_channel_id,
                    from_chat_id=from_chat_id,
                    message_id=ids[0],
                )
            )
            chat = getattr(sent, "chat", None)
            if chat is None:
                chat = await bot.get_chat(tz_channel_id)
            return PublishedToTzChannel(message_id=sent.message_id, chat=chat)
        copied = await _call_with_flood_retry(
            lambda: bot.copy_messages(
                chat_id=tz_channel_id,
                from_chat_id=from_chat_id,
                message_ids=ids,
            )
        )
        if not copied:
            raise TzPublishError("copy_messages returned empty result")
        first = copied[0]
        message_id = getattr(first, "message_id", None) or first
        chat = await bot.get_chat(tz_channel_id)
        return PublishedToTzChannel(message_id=int(message_id), chat=chat)
    except TzPublishError:
        raise
    except Exception as exc:
        raise TzPublishError(f"failed to copy post to tz channel: {exc}") from exc


async def _forward_messages(
        bot: Bot,
        *,
        tz_channel_id: int,
        from_chat_id: int,
        message_ids: list[int],
) -> PublishedToTzChannel:
    try:
        ids = sorted(set(message_ids))
        if not ids:
            raise TzPublishError("no message ids to forward")
        if len(ids) == 1:
            sent = await bot.forward_message(
                chat_id=tz_channel_id,
                from_chat_id=from_chat_id,
                message_id=ids[0],
            )
            chat = getattr(sent, "chat", None)
            if chat is None:
                chat = await bot.get_chat(tz_channel_id)
            return PublishedToTzChannel(message_id=sent.message_id, chat=chat)
        forwarded = await bot.forward_messages(
            chat_id=tz_channel_id,
            from_chat_id=from_chat_id,
            message_ids=ids,
        )
        if not forwarded:
            raise TzPublishError("forward_messages returned empty result")
        first = forwarded[0]
        message_id = getattr(first, "message_id", None) or first
        chat = await bot.get_chat(tz_channel_id)
        return PublishedToTzChannel(message_id=int(message_id), chat=chat)
    except TzPublishError:
        raise
    except Exception as exc:
        raise TzPublishError(f"failed to forward post to tz channel: {exc}") from exc


async def _send_composed_post(bot: Bot, *, tz_channel_id: int, post: BotPostDraft) -> PublishedToTzChannel:
    media_parts = [m for m in post.media if m.file_id]
    caption = post.text
    try:
        if not media_parts:
            if not post.text:
                raise TzPublishError("post has no source messages and no content")
            sent = await bot.send_message(chat_id=tz_channel_id, text=post.text)
            return PublishedToTzChannel(message_id=sent.message_id, chat=sent.chat)

        if len(media_parts) == 1:
            part = media_parts[0]
            if part.content_type == "photo":
                sent = await bot.send_photo(
                    chat_id=tz_channel_id, photo=part.file_id, caption=caption,
                )
            elif part.content_type == "video":
                sent = await bot.send_video(
                    chat_id=tz_channel_id, video=part.file_id, caption=caption,
                )
            else:
                sent = await bot.send_document(
                    chat_id=tz_channel_id, document=part.file_id, caption=caption,
                )
            return PublishedToTzChannel(message_id=sent.message_id, chat=sent.chat)

        input_media = []
        for idx, part in enumerate(media_parts):
            part_caption = caption if idx == 0 else None
            if part.content_type == "photo":
                input_media.append(InputMediaPhoto(media=part.file_id, caption=part_caption))
            elif part.content_type == "video":
                input_media.append(InputMediaVideo(media=part.file_id, caption=part_caption))
            else:
                input_media.append(InputMediaDocument(media=part.file_id, caption=part_caption))
        sent_group = await bot.send_media_group(chat_id=tz_channel_id, media=input_media)
        if not sent_group:
            raise TzPublishError("send_media_group returned empty result")
        return PublishedToTzChannel(message_id=sent_group[0].message_id, chat=sent_group[0].chat)
    except TzPublishError:
        raise
    except Exception as exc:
        raise TzPublishError(f"failed to publish composed post to tz channel: {exc}") from exc
