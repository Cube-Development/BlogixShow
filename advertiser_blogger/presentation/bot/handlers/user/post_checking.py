from __future__ import annotations

import re
from structlog import get_logger
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.types import Message
from dishka import FromDishka

from advertiser_blogger.application.events.verify_post_scheduled.dto import VerifyOrderKind
from advertiser_blogger.application.interactors_bot.run_post_checking.dto import (
    PostCheckingCard,
    RunPostCheckingDtoInput,
)
from advertiser_blogger.application.interactors_bot.run_post_checking.use_case import RunPostCheckingInteractor
from advertiser_blogger.domain.read.constants import Language
from advertiser_blogger.infrastructure.bot.templates.template_factory import BotTemplate, BotTemplateFactory
from advertiser_blogger.presentation.bot.handlers.user.bot_membership import (
    ALLOWED_BOT_MEMBERSHIP_USER_IDS,
)
from configuration.common import CommonConfig
from configuration.secret import GroupTopic

logger = get_logger(__name__)

PostCheckingRouter = Router(name="PostCheckingRouter")

KEYWORD = "post checking"
POST_VERIFY_TOPIC = "PostVerify"
TG_MESSAGE_LIMIT = 4096
UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
)
FORCED_FOOTER = (
    "РК: <code>{project_id}</code>\n"
    "Проверка: принудительная"
)


def _extract_project_ids(text: str) -> list[UUID]:
    lower = text.lower()
    idx = lower.find(KEYWORD)
    body = text[idx + len(KEYWORD) :] if idx >= 0 else text
    out: list[UUID] = []
    seen: set[UUID] = set()
    for raw in UUID_RE.findall(body):
        project_id = UUID(raw)
        if project_id in seen:
            continue
        seen.add(project_id)
        out.append(project_id)
    return out


def _topic_id(topics: list[GroupTopic], name: str) -> int | None:
    for topic in topics:
        if topic.name == name:
            return topic.topic_id
    return None


def _split_messages(text: str, limit: int = TG_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            parts.append(rest)
            break
        cut = rest.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return parts


def _card_body(template: BotTemplate, card: PostCheckingCard) -> str:
    result = card.result
    if result.kind == VerifyOrderKind.ok:
        body = template.post_verify_ok(
            order_id=result.order_id,
            channel_url=result.channel_url,
            publish_date=result.publish_date,
            publish_time=result.publish_time,
            score=result.score,
            post_url=result.post_url,
            source=result.source,
        )
    elif result.kind == VerifyOrderKind.mismatch:
        body = template.post_verify_mismatch(
            order_id=result.order_id,
            channel_url=result.channel_url,
            publish_date=result.publish_date,
            publish_time=result.publish_time,
            score=result.score,
            post_url=result.post_url,
        )
    else:
        body = template.post_not_found(
            order_id=result.order_id,
            channel_url=result.channel_url,
            publish_date=result.publish_date,
            publish_time=result.publish_time,
        )
    return body + "\n" + FORCED_FOOTER.format(project_id=card.project_id)


@PostCheckingRouter.message(
    F.from_user.id.in_(ALLOWED_BOT_MEMBERSHIP_USER_IDS),
    F.text.func(lambda t: bool(t) and t.lstrip().lower().startswith(KEYWORD)),
)
async def check_posts(
        message: Message,
        interactor: FromDishka[RunPostCheckingInteractor],
        bot: FromDishka[Bot],
        config: FromDishka[CommonConfig],
        bot_templates: FromDishka[BotTemplateFactory],
) -> None:
    assert message.text is not None
    project_ids = _extract_project_ids(message.text)
    if not project_ids:
        await message.answer(
            "После «post checking» укажи UUID РК:\n"
            "post checking\n"
            "<uuid>\n"
            "<uuid>",
        )
        return
    output = await interactor(data=RunPostCheckingDtoInput(project_ids=project_ids))
    for chunk in _split_messages(output.header):
        await message.answer(chunk)
    for error in output.errors:
        for chunk in _split_messages(error):
            await message.answer(chunk)

    template = bot_templates(Language.ru)
    topic_id = _topic_id(config.bot.topics, POST_VERIFY_TOPIC)
    if topic_id is None:
        logger.warning("group notification topic not found", topic=POST_VERIFY_TOPIC)
    target_chat_id = config.bot.events_group_chat_id
    already_in_post_verify = (
        topic_id is not None
        and message.chat.id == target_chat_id
        and message.message_thread_id == topic_id
    )

    for card in output.cards:
        text = _card_body(template, card)
        await message.answer(text)
        if topic_id is None or already_in_post_verify:
            continue
        try:
            await bot.send_message(
                chat_id=target_chat_id,
                text=text,
                message_thread_id=topic_id,
            )
        except Exception:
            logger.exception("post verify card send failed", target_chat_id=target_chat_id, topic_id=topic_id, order_id=card.result.order_id)
