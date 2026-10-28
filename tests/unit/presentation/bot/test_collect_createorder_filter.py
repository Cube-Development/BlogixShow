import asyncio
from unittest.mock import AsyncMock, MagicMock

from advertiser_blogger.presentation.bot.filters.post_submission import IsPostSubmission


def test_post_submission_disabled_in_collect_state() -> None:
    async def _run():
        filt = IsPostSubmission()
        state = AsyncMock()
        state.get_state = AsyncMock(return_value="CollectCreateorderState:awaiting_post")
        message = MagicMock()
        message.chat.type = "private"
        message.text = "https://t.me/channel/123"
        message.caption = None
        assert await filt(message, state) is False

    asyncio.run(_run())
