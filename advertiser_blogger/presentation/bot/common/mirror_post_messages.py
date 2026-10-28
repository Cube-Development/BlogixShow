"""Mirror user creatives as bot-owned messages (premium emoji / TZ forward)."""

from __future__ import annotations

from structlog import get_logger

from aiogram import Bot

logger = get_logger(__name__)


async def mirror_post_messages(
        bot: Bot,
        *,
        chat_id: int,
        source_message_ids: list[int],
) -> list[int]:
    """Copy user messages into the same chat as bot-owned messages. Returns new ids."""
    ids = sorted(set(source_message_ids or []))
    if not ids:
        return []
    try:
        if len(ids) == 1:
            sent = await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=chat_id,
                message_id=ids[0],
            )
            return [sent.message_id]
        copied = await bot.copy_messages(
            chat_id=chat_id,
            from_chat_id=chat_id,
            message_ids=ids,
        )
        if not copied:
            return []
        return [m.message_id for m in copied]
    except Exception:
        logger.exception("mirror post messages failed", chat_id=chat_id, ids=ids)
        return []


async def delete_bot_mirror_messages(
        bot: Bot,
        *,
        chat_id: int,
        bot_message_ids: list[int],
) -> None:
    ids = sorted(set(bot_message_ids or []))
    if not ids:
        return
    try:
        await bot.delete_messages(chat_id=chat_id, message_ids=ids)
    except Exception:
        for mid in ids:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass
