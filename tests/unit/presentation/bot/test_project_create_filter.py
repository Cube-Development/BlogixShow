import asyncio
from unittest.mock import AsyncMock, MagicMock

from advertiser_blogger.presentation.bot.filters.project_create import IsProjectCreateCollectInput


def test_collect_input_rejects_commands_and_menu():
    async def _run():
        filt = IsProjectCreateCollectInput()
        state = AsyncMock()
        state.get_state = AsyncMock(return_value="ProjectCreateState:awaiting_post")

        for text in ("/start", "Активные проекты", "🚀 Активные проекты", "Отмена"):
            message = MagicMock()
            message.text = text
            message.caption = None
            assert await filt(message, state) is False

    asyncio.run(_run())


def test_collect_input_accepts_creative_text():
    async def _run():
        filt = IsProjectCreateCollectInput()
        state = AsyncMock()
        state.get_state = AsyncMock(return_value="ProjectCreateState:awaiting_post")

        message = MagicMock()
        message.text = "Проект: test\n@channel"
        message.caption = None
        assert await filt(message, state) is True

    asyncio.run(_run())


def test_collect_input_false_outside_project_create_state():
    async def _run():
        filt = IsProjectCreateCollectInput()
        state = AsyncMock()
        state.get_state = AsyncMock(return_value="BloggerState:publish")

        message = MagicMock()
        message.text = "hello"
        message.caption = None
        assert await filt(message, state) is False

    asyncio.run(_run())
