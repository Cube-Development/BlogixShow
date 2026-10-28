from unittest.mock import AsyncMock, MagicMock, patch

from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import CreativeKind
from advertiser_blogger.application.interactors_bot.project_create.media_upload import (
    ProjectPostMediaUploader,
)
from advertiser_blogger.application.interactors_bot.project_create.models import BotPostDraft
from advertiser_blogger.application.interactors_bot.project_create.publish_tz import (
    PublishedToTzChannel,
)


def test_skip_kind_does_not_sleep() -> None:
    import asyncio

    uploader = ProjectPostMediaUploader(bot=MagicMock(), tz_channel_id=-1)
    post = BotPostDraft(local_id="empty", kind=CreativeKind.empty)
    with patch(
        "advertiser_blogger.application.interactors_bot.project_create.media_upload.asyncio.sleep",
        new_callable=AsyncMock,
    ) as sleep:
        asyncio.run(uploader(post, telegram_chat_id=1))
        sleep.assert_not_awaited()


def test_tz_publish_sleeps_after_success() -> None:
    import asyncio

    uploader = ProjectPostMediaUploader(bot=MagicMock(), tz_channel_id=-100)
    post = BotPostDraft(local_id="media", kind=CreativeKind.media, source_message_ids=[1])
    published = PublishedToTzChannel(message_id=9, chat=None)
    with (
        patch(
            "advertiser_blogger.application.interactors_bot.project_create.media_upload.publish_draft_post_to_channel",
            new_callable=AsyncMock,
            return_value=published,
        ),
        patch(
            "advertiser_blogger.application.interactors_bot.project_create.media_upload.resolve_published_post_url",
            new_callable=AsyncMock,
            return_value="https://t.me/c/1/9",
        ),
        patch(
            "advertiser_blogger.application.interactors_bot.project_create.media_upload.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep,
    ):
        asyncio.run(uploader(post, telegram_chat_id=1))
        sleep.assert_awaited_once()
