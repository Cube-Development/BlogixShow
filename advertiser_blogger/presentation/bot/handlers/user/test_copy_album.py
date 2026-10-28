from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message
from dishka import FromDishka

from advertiser_blogger.domain.common.telegram_post_url import resolve_expected_from_tz
from advertiser_blogger.infrastructure.parsers.telegram_public_channel_album_ids import (
    TelegramPublicChannelAlbumIdsProvider,
)
from advertiser_blogger.presentation.bot.handlers.user.user import extract_post_id
from configuration.common import CommonConfig

TestCopyAlbumRouter = Router(name="TestCopyAlbumRouter")

# telegram user id, которым разрешён test copy album
ALLOWED_TEST_COPY_ALBUM_USER_IDS: frozenset[int] = frozenset({
    682399039,
    60644557,
    168530165,
    163077296,
})

KEYWORD = "test album"
_BLOGIX_POSTS_USERNAME = "blogix_posts"


@TestCopyAlbumRouter.message(
    F.from_user.id.in_(ALLOWED_TEST_COPY_ALBUM_USER_IDS),
    F.text.func(lambda t: bool(t) and t.lstrip().lower().startswith(KEYWORD)),
)
async def test_copy_album(
        message: Message,
        bot: FromDishka[Bot],
        album_ids_provider: FromDishka[TelegramPublicChannelAlbumIdsProvider],
        config: FromDishka[CommonConfig],
) -> None:
    assert message.text is not None
    post_url, _ = resolve_expected_from_tz(tz_text=message.text)
    post_telegram_id = (
        extract_post_id(url=post_url, channel_username=_BLOGIX_POSTS_USERNAME)
        if post_url is not None
        else None
    )
    if post_url is None or post_telegram_id is None:
        await message.answer(
            "После «test album» укажи ссылку blogix_posts:\n"
            "test album https://t.me/blogix_posts/1082",
        )
        return

    tz_channel_id = config.bot_project.tz_channel_id
    message_ids = await album_ids_provider.fetch_album_message_ids(post_url)
    if not message_ids:
        message_ids = [post_telegram_id]

    chat_id = message.chat.id
    try:
        if len(message_ids) == 1:
            await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=tz_channel_id,
                message_id=message_ids[0],
            )
        else:
            await bot.copy_messages(
                chat_id=chat_id,
                from_chat_id=tz_channel_id,
                message_ids=message_ids,
            )
    except TelegramAPIError as exc:
        await message.answer(
            f"copy failed ids={message_ids} from={tz_channel_id}: {exc}",
        )
        return

    await message.answer(f"copied {len(message_ids)} msg(s): {message_ids} from={tz_channel_id}")
