from __future__ import annotations

import asyncio

from aiogram import Bot

from advertiser_blogger.application.common.application.post.post_convert import FileObject
from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import (
    CreativeKind,
    skips_tz_channel_publish,
)
from advertiser_blogger.application.interactors_bot.project_create.models import BotPostDraft, PublishMode
from advertiser_blogger.application.interactors_bot.project_create.publish_tz import (
    format_tz_html,
    publish_draft_post_to_channel,
    resolve_published_post_url,
)
from advertiser_blogger.domain.record.order.constants import ContentType

TZ_CHANNEL_PUBLISH_DELAY_SEC = 0.5


class ProjectPostMediaUploader:
    """Publish draft post to TZ channel (or keep button/repost text) as PostText."""

    def __init__(self, bot: Bot, tz_channel_id: int):
        self.bot = bot
        self.tz_channel_id = tz_channel_id

    async def __call__(
            self,
            post: BotPostDraft,
            *,
            telegram_chat_id: int,
            publish_mode: PublishMode | None = None,
    ) -> list[FileObject]:
        if skips_tz_channel_publish(post.kind):
            if post.kind == CreativeKind.empty:
                content = " "
            else:
                content = (post.text or "").strip() or " "
                if post.kind == CreativeKind.repost:
                    content = format_tz_html(content)
            return [
                FileObject(content_type=ContentType.text, content=content, name=None),
            ]

        published = await publish_draft_post_to_channel(
            self.bot,
            tz_channel_id=self.tz_channel_id,
            user_chat_id=telegram_chat_id,
            post=post,
            publish_mode=publish_mode,
        )
        post_url = await resolve_published_post_url(
            self.bot,
            channel_id=self.tz_channel_id,
            message_id=published.message_id,
            chat=published.chat,
        )
        await asyncio.sleep(TZ_CHANNEL_PUBLISH_DELAY_SEC)
        return [
            FileObject(content_type=ContentType.text, content=format_tz_html(post_url), name=None),
        ]
