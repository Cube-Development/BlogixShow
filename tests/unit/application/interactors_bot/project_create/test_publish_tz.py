from unittest.mock import AsyncMock, MagicMock

from aiogram.enums import ChatType
from aiogram.types import Chat

from advertiser_blogger.application.interactors_bot.project_create.models import BotPostDraft, PublishMode
from advertiser_blogger.application.interactors_bot.project_create.publish_tz import (
    PublishedToTzChannel,
    format_tz_html,
    publish_draft_post_to_channel,
    resolve_published_post_url,
)


def test_format_tz_html_wraps_url() -> None:
    assert format_tz_html("https://t.me/testblogix_5/42") == "<p>https://t.me/testblogix_5/42</p>"


def test_resolve_published_post_url_uses_chat_username() -> None:
    import asyncio

    bot = MagicMock()

    async def _run() -> str:
        chat = Chat(id=-1009876543210, type=ChatType.CHANNEL, username="testblogix_5")
        return await resolve_published_post_url(
            bot,
            channel_id=-1009876543210,
            message_id=42,
            chat=chat,
        )

    assert asyncio.run(_run()) == "https://t.me/testblogix_5/42"
    bot.get_chat.assert_not_called()


def test_resolve_published_post_url_fetches_chat_when_username_missing() -> None:
    import asyncio

    async def _run() -> str:
        bot = MagicMock()
        bot.get_chat = AsyncMock(
            return_value=Chat(id=-1009876543210, type=ChatType.CHANNEL, username="testblogix_5"),
        )
        return await resolve_published_post_url(
            bot,
            channel_id=-1009876543210,
            message_id=35,
            chat=None,
        )

    assert asyncio.run(_run()) == "https://t.me/testblogix_5/35"


def test_resolve_published_post_url_falls_back_to_private_link() -> None:
    import asyncio

    async def _run() -> str:
        bot = MagicMock()
        bot.get_chat = AsyncMock(
            return_value=Chat(id=-1009876543210, type=ChatType.CHANNEL, username=None),
        )
        return await resolve_published_post_url(
            bot,
            channel_id=-1009876543210,
            message_id=35,
            chat=None,
        )

    assert asyncio.run(_run()) == "https://t.me/c/3761698209/35"


def test_publish_forwards_bot_mirror_first() -> None:
    import asyncio

    async def _run() -> tuple[PublishedToTzChannel, MagicMock]:
        bot = MagicMock()
        chat = Chat(id=-1009876543210, type=ChatType.CHANNEL, username="testblogix_5")
        sent = MagicMock(message_id=99, chat=chat)
        bot.forward_message = AsyncMock(return_value=sent)
        bot.forward_messages = AsyncMock()
        post = BotPostDraft(
            local_id="p1",
            source_message_ids=[10],
            bot_message_ids=[55],
        )
        published = await publish_draft_post_to_channel(
            bot,
            tz_channel_id=-1009876543210,
            user_chat_id=123,
            post=post,
        )
        return published, bot

    published, bot = asyncio.run(_run())
    assert published.message_id == 99
    bot.forward_message.assert_awaited_once_with(
        chat_id=-1009876543210,
        from_chat_id=123,
        message_id=55,
    )


def test_publish_forwards_user_source_when_mirror_fails() -> None:
    import asyncio

    async def _run() -> tuple[PublishedToTzChannel, MagicMock]:
        bot = MagicMock()
        chat = Chat(id=-1009876543210, type=ChatType.CHANNEL, username="testblogix_5")
        sent = MagicMock(message_id=88, chat=chat)
        bot.forward_message = AsyncMock(side_effect=[RuntimeError("gone"), sent])
        post = BotPostDraft(
            local_id="p1",
            source_message_ids=[10],
            bot_message_ids=[55],
        )
        published = await publish_draft_post_to_channel(
            bot,
            tz_channel_id=-1009876543210,
            user_chat_id=123,
            post=post,
        )
        return published, bot

    published, bot = asyncio.run(_run())
    assert published.message_id == 88
    assert bot.forward_message.await_count == 2


def test_publish_forwards_single_source_message() -> None:
    import asyncio

    async def _run() -> tuple[PublishedToTzChannel, MagicMock]:
        bot = MagicMock()
        chat = Chat(id=-1009876543210, type=ChatType.CHANNEL, username="testblogix_5")
        sent = MagicMock(message_id=99, chat=chat)
        bot.forward_message = AsyncMock(return_value=sent)
        post = BotPostDraft(local_id="p1", source_message_ids=[10])
        published = await publish_draft_post_to_channel(
            bot,
            tz_channel_id=-1009876543210,
            user_chat_id=123,
            post=post,
        )
        return published, bot

    published, bot = asyncio.run(_run())
    assert published.message_id == 99
    assert published.chat.username == "testblogix_5"
    bot.forward_message.assert_awaited_once_with(
        chat_id=-1009876543210,
        from_chat_id=123,
        message_id=10,
    )


def test_publish_forwards_album_messages() -> None:
    import asyncio

    async def _run() -> tuple[PublishedToTzChannel, MagicMock]:
        bot = MagicMock()
        bot.forward_messages = AsyncMock(
            return_value=[MagicMock(message_id=101), MagicMock(message_id=102)],
        )
        bot.get_chat = AsyncMock(
            return_value=Chat(id=-1009876543210, type=ChatType.CHANNEL, username="testblogix_5"),
        )
        post = BotPostDraft(local_id="p1", source_message_ids=[12, 10, 11])
        published = await publish_draft_post_to_channel(
            bot,
            tz_channel_id=-1009876543210,
            user_chat_id=123,
            post=post,
        )
        return published, bot

    published, bot = asyncio.run(_run())
    assert published.message_id == 101
    assert published.chat.username == "testblogix_5"
    bot.forward_messages.assert_awaited_once_with(
        chat_id=-1009876543210,
        from_chat_id=123,
        message_ids=[10, 11, 12],
    )
    bot.get_chat.assert_awaited_once_with(-1009876543210)


def test_publish_copy_uses_source_and_ignores_bot_mirror() -> None:
    import asyncio

    async def _run() -> tuple[PublishedToTzChannel, MagicMock]:
        bot = MagicMock()
        chat = Chat(id=-1009876543210, type=ChatType.CHANNEL, username="testblogix_5")
        sent = MagicMock(message_id=77, chat=chat)
        bot.copy_message = AsyncMock(return_value=sent)
        bot.forward_message = AsyncMock()
        post = BotPostDraft(
            local_id="p1",
            source_message_ids=[10],
            bot_message_ids=[55],
        )
        published = await publish_draft_post_to_channel(
            bot,
            tz_channel_id=-1009876543210,
            user_chat_id=123,
            post=post,
            publish_mode=PublishMode.copy,
        )
        return published, bot

    published, bot = asyncio.run(_run())
    assert published.message_id == 77
    bot.copy_message.assert_awaited_once_with(
        chat_id=-1009876543210,
        from_chat_id=123,
        message_id=10,
    )
    bot.forward_message.assert_not_awaited()


def test_publish_copy_album_messages() -> None:
    import asyncio

    async def _run() -> tuple[PublishedToTzChannel, MagicMock]:
        bot = MagicMock()
        bot.copy_messages = AsyncMock(
            return_value=[MagicMock(message_id=201), MagicMock(message_id=202)],
        )
        bot.get_chat = AsyncMock(
            return_value=Chat(id=-1009876543210, type=ChatType.CHANNEL, username="testblogix_5"),
        )
        bot.forward_messages = AsyncMock()
        post = BotPostDraft(local_id="p1", source_message_ids=[12, 10, 11])
        published = await publish_draft_post_to_channel(
            bot,
            tz_channel_id=-1009876543210,
            user_chat_id=123,
            post=post,
            publish_mode=PublishMode.copy,
        )
        return published, bot

    published, bot = asyncio.run(_run())
    assert published.message_id == 201
    bot.copy_messages.assert_awaited_once_with(
        chat_id=-1009876543210,
        from_chat_id=123,
        message_ids=[10, 11, 12],
    )
    bot.forward_messages.assert_not_awaited()


def _telegram_retry_after(seconds: int = 1):
    from aiogram.exceptions import TelegramRetryAfter

    try:
        return TelegramRetryAfter(
            method=MagicMock(),
            message=f"Flood control exceeded. Retry in {seconds} seconds",
        )
    except TypeError:
        err = TelegramRetryAfter.__new__(TelegramRetryAfter)
        err.retry_after = seconds
        return err


def test_publish_copy_retries_flood_without_send_photo(monkeypatch) -> None:
    import asyncio

    async def _run() -> tuple[PublishedToTzChannel, MagicMock]:
        bot = MagicMock()
        chat = Chat(id=-1009876543210, type=ChatType.CHANNEL, username="testblogix_5")
        sent = MagicMock(message_id=77, chat=chat)
        bot.copy_message = AsyncMock(side_effect=[_telegram_retry_after(0), sent])
        bot.send_photo = AsyncMock()
        monkeypatch.setattr(
            "advertiser_blogger.application.interactors_bot.project_create.publish_tz.asyncio.sleep",
            AsyncMock(),
        )
        post = BotPostDraft(local_id="p1", source_message_ids=[10])
        published = await publish_draft_post_to_channel(
            bot,
            tz_channel_id=-1009876543210,
            user_chat_id=123,
            post=post,
            publish_mode=PublishMode.copy,
        )
        return published, bot

    published, bot = asyncio.run(_run())
    assert published.message_id == 77
    assert bot.copy_message.await_count == 2
    bot.send_photo.assert_not_awaited()

