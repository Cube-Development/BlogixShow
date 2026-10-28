from structlog import get_logger

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMemberUpdated
from dishka import FromDishka

from advertiser_blogger.presentation.bot.common.forward_message import (
    telegram_chat_id_to_channel_ident,
)
from configuration.common import CommonConfig
from configuration.secret import GroupTopic

logger = get_logger(__name__)

MyChatMemberRouter = Router(name="MyChatMemberRouter")

BOT_MEMBERSHIP_TOPIC = "BotMembership"

ADMIN_STATUSES = {
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}

# права ChatMemberAdministrator / полезные флаги для каналов
PERMISSION_ATTRS = (
    "can_be_edited",
    "is_anonymous",
    "can_manage_chat",
    "can_delete_messages",
    "can_manage_video_chats",
    "can_restrict_members",
    "can_promote_members",
    "can_change_info",
    "can_invite_users",
    "can_post_stories",
    "can_edit_stories",
    "can_delete_stories",
    "can_post_messages",
    "can_edit_messages",
    "can_pin_messages",
    "can_manage_topics",
)


def _topic_id(topics: list[GroupTopic], name: str) -> int | None:
    for topic in topics:
        if topic.name == name:
            return topic.topic_id
    return None


def _chat_link(event: ChatMemberUpdated) -> str | None:
    chat = event.chat
    if chat.username:
        return f"https://t.me/{chat.username}"
    if chat.type in (ChatType.CHANNEL, ChatType.SUPERGROUP):
        ident = telegram_chat_id_to_channel_ident(chat.id)
        return f"https://t.me/c/{ident}"
    return None


def _status_value(member) -> str:
    status = member.status
    return status.value if hasattr(status, "value") else str(status)


def _format_permissions(member) -> str:
    lines: list[str] = []
    for attr in PERMISSION_ATTRS:
        if hasattr(member, attr):
            value = getattr(member, attr)
            mark = "✅" if value else "❌"
            lines.append(f"  {mark} {attr}: {value}")
    if not lines:
        return "  (нет списка прав для этого статуса)"
    return "\n".join(lines)


def _format_membership_message(event: ChatMemberUpdated) -> str:
    old = event.old_chat_member
    new = event.new_chat_member
    chat = event.chat
    actor = event.from_user
    is_admin = new.status in ADMIN_STATUSES
    link = _chat_link(event)
    header_mark = "✅" if is_admin else "❌"

    actor_line = ""
    if actor is not None:
        username = f"@{actor.username}" if actor.username else "—"
        actor_line = f"Кто изменил: {actor.id} ({username})\n"

    link_line = f"url: {link}\n" if link else "url: —\n"

    return (
        f"{header_mark} <b>Bot membership</b>\n"
        f"Чат: {chat.title or '—'}\n"
        f"chat_id: <code>{chat.id}</code>\n"
        f"{link_line}"
        f"status: {_status_value(old)} → <b>{_status_value(new)}</b>\n"
        f"is_admin: {is_admin}\n"
        f"{actor_line}"
        f"Права бота:\n{_format_permissions(new)}"
    )


@MyChatMemberRouter.my_chat_member()
async def on_bot_chat_member_updated(
        event: ChatMemberUpdated,
        bot: FromDishka[Bot],
        config: FromDishka[CommonConfig],
) -> None:
    old_status = _status_value(event.old_chat_member)
    new_status = _status_value(event.new_chat_member)
    logger.info("bot membership changed", chat_id=event.chat.id, chat_type=event.chat.type, old_status=old_status, new_status=new_status)

    topic_id = _topic_id(config.bot.topics, BOT_MEMBERSHIP_TOPIC)
    if topic_id is None:
        logger.warning("group notification topic not found", topic=BOT_MEMBERSHIP_TOPIC)
        return

    target_chat_id = config.bot.events_group_chat_id
    text = _format_membership_message(event)
    try:
        await bot.send_message(
            chat_id=target_chat_id,
            text=text,
            message_thread_id=topic_id,
        )
    except Exception:
        logger.exception("bot membership event send failed", target_chat_id=target_chat_id, topic_id=topic_id, source_chat_id=event.chat.id)
