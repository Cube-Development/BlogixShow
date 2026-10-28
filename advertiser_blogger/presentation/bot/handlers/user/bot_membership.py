from __future__ import annotations

import asyncio
import re

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import Message
from dishka import FromDishka

BotMembershipRouter = Router(name="BotMembershipRouter")

# telegram user id, которым разрешена проверка bot membership
ALLOWED_BOT_MEMBERSHIP_USER_IDS: frozenset[int] = frozenset(
    {
        682399039,
        60644557,
        168530165,
        163077296,
        8100500164,
        1762987232,
        8358735188,
        # 123456789,
    }
)

KEYWORD = "bot membership"
ADMIN_STATUSES = {
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}
TG_MESSAGE_LIMIT = 4096

USERNAME_RE = re.compile(
    r"^(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{4,})/?$",
    re.I,
)
TOKEN_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/[A-Za-z0-9_]{4,}/?|"
    r"@[A-Za-z0-9_]{4,}|"
    r"-?\d{5,}",
    re.I,
)


def _parse_target(raw: int | str) -> int | str:
    if isinstance(raw, int):
        value = raw
        value_str = str(value)
        if value_str.startswith("-100") or value < 0:
            return value
        return int(f"-100{value}")

    s = str(raw).strip()
    if not s:
        raise ValueError("empty")
    if s.startswith("@"):
        return s
    m = USERNAME_RE.match(s)
    if m:
        return f"@{m.group(1)}"
    if re.fullmatch(r"-?\d+", s):
        return _parse_target(int(s))
    raise ValueError(f"не понял цель: {raw!r}")


def _extract_targets(text: str) -> list[int | str]:
    lower = text.lower()
    idx = lower.find(KEYWORD)
    body = text[idx + len(KEYWORD) :] if idx >= 0 else text

    out: list[int | str] = []
    seen: set[str] = set()
    for raw in TOKEN_RE.findall(body):
        try:
            target = _parse_target(raw)
        except ValueError:
            continue
        key = str(target)
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
    return out


def _clip(text: str, limit: int = TG_MESSAGE_LIMIT) -> str:
    if len(text) <= limit:
        return text
    suffix = "\n… truncated"
    return text[: limit - len(suffix)] + suffix


async def _check_one(bot: Bot, bot_id: int, target: int | str) -> tuple[bool, str]:
    label = str(target)
    try:
        chat = await bot.get_chat(target)
        member = await bot.get_chat_member(chat_id=chat.id, user_id=bot_id)
        status = member.status
        title = getattr(chat, "title", None) or "?"
        username = getattr(chat, "username", None)
        link = f"@{username}" if username else label
        can_post = getattr(member, "can_post_messages", None)
        is_admin = status in ADMIN_STATUSES
        note = ""
        if is_admin and chat.type != ChatType.CHANNEL:
            note = " (не channel)"
        line = (
            f"{'✅' if is_admin else '❌'} {link} | {title!r} | "
            f"status={status} | can_post={can_post}{note}"
        )
        return is_admin, line
    except TelegramForbiddenError as exc:
        return False, f"❌ {label} | FORBIDDEN: {exc}"
    except TelegramAPIError as exc:
        return False, f"❌ {label} | API_ERROR: {exc}"
    except Exception as exc:
        return False, f"❌ {label} | ERROR: {type(exc).__name__}: {exc}"


@BotMembershipRouter.message(
    F.from_user.id.in_(ALLOWED_BOT_MEMBERSHIP_USER_IDS),
    F.text.func(lambda t: bool(t) and t.lstrip().lower().startswith(KEYWORD)),
)
async def check_bot_membership(message: Message, bot: FromDishka[Bot]) -> None:
    assert message.text is not None
    targets = _extract_targets(message.text)
    if not targets:
        await message.answer(
            "После «bot membership» укажи каналы:\n@name / https://t.me/name / chat_id",
        )
        return

    me = await bot.get_me()
    lines: list[str] = []
    admin_count = 0
    for target in targets:
        is_admin, line = await _check_one(bot=bot, bot_id=me.id, target=target)
        if is_admin:
            admin_count += 1
        lines.append(line)
        await asyncio.sleep(0.05)

    header = f"Bot membership: {admin_count}/{len(targets)} admin\n\n"
    await message.answer(_clip(header + "\n".join(lines)))
