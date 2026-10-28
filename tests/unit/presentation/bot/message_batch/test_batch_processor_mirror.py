from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from advertiser_blogger.application.interactors_bot.project_create.models import PublishMode
from advertiser_blogger.presentation.bot.message_batch.batch_processor import (
    process_project_create_message_batch,
)
from advertiser_blogger.presentation.bot.message_batch.models import MessageBatch


def _photo_msg(message_id: int, *, chat_id: int = 100) -> MagicMock:
    message = MagicMock()
    message.message_id = message_id
    message.chat.id = chat_id
    message.text = None
    message.caption = "ad"
    message.media_group_id = None
    message.photo = [SimpleNamespace(file_id="p1")]
    message.video = None
    message.document = None
    message.animation = None
    message.reply_to_message = None
    message.from_user = SimpleNamespace(id=42)
    return message


def _install_fake_project_create_handlers() -> types.ModuleType:
    """Avoid importing real handlers package (heavy DB deps) inside batch_processor."""
    fake = types.ModuleType(
        "advertiser_blogger.presentation.bot.handlers.user.project_create",
    )
    fake._maybe_show_preview_or_ask_tz = AsyncMock()
    fake._apply_metadata_and_maybe_preview = AsyncMock()
    fake._bind_head_if_awaiting_creative = AsyncMock(return_value=False)
    fake._continue_after_batch = AsyncMock()
    for name in (
        "advertiser_blogger.presentation.bot.handlers",
        "advertiser_blogger.presentation.bot.handlers.user",
    ):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    sys.modules[
        "advertiser_blogger.presentation.bot.handlers.user.project_create"
    ] = fake
    return fake


def test_create_post_mirrors_once() -> None:
    async def _run() -> None:
        _install_fake_project_create_handlers()
        msg = _photo_msg(10)
        batch = MessageBatch(
            chat_id=100,
            messages=[msg],
            created_at=datetime.now(tz=timezone.utc),
        )
        user = SimpleNamespace(id=uuid4(), language="ru")
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={})
        state.update_data = AsyncMock()
        bot = MagicMock()
        mirror = AsyncMock(return_value=[999])

        with (
            patch(
                "advertiser_blogger.presentation.bot.message_batch.batch_processor.load_draft",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "advertiser_blogger.presentation.bot.message_batch.batch_processor.save_draft",
                new=AsyncMock(),
            ) as save_draft,
            patch(
                "advertiser_blogger.presentation.bot.message_batch.batch_processor.mirror_post_messages",
                new=mirror,
            ),
        ):
            await process_project_create_message_batch(
                batch=batch,
                state=state,
                user=user,
                resolve_channels=MagicMock(),
                config=MagicMock(),
                inline=MagicMock(),
                bot=bot,
            )

        mirror.assert_awaited_once()
        assert mirror.await_args.kwargs["chat_id"] == 100
        assert mirror.await_args.kwargs["source_message_ids"] == [10]
        saved_draft = save_draft.await_args.args[1]
        assert len(saved_draft.posts) == 1
        assert saved_draft.posts[0].bot_message_ids == [999]

    asyncio.run(_run())


def test_create_post_skips_mirror_when_already_mirrored() -> None:
    async def _run() -> None:
        _install_fake_project_create_handlers()
        msg = _photo_msg(10)
        batch = MessageBatch(
            chat_id=100,
            messages=[msg],
            created_at=datetime.now(tz=timezone.utc),
        )
        user = SimpleNamespace(id=uuid4(), language="ru")
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={})
        state.update_data = AsyncMock()
        bot = MagicMock()
        mirror = AsyncMock(return_value=[999])

        existing_post = MagicMock()
        existing_post.source_message_ids = [10]
        existing_post.bot_message_ids = [555]
        existing_post.local_id = "p1"
        existing_post.channels = []
        existing_draft = MagicMock()
        existing_draft.posts = [existing_post]
        existing_draft.active_post_id = "p1"

        with (
            patch(
                "advertiser_blogger.presentation.bot.message_batch.batch_processor.load_draft",
                new=AsyncMock(return_value=existing_draft),
            ),
            patch(
                "advertiser_blogger.presentation.bot.message_batch.batch_processor.append_post_from_message",
                new=MagicMock(return_value=existing_post),
            ),
            patch(
                "advertiser_blogger.presentation.bot.message_batch.batch_processor.save_draft",
                new=AsyncMock(),
            ),
            patch(
                "advertiser_blogger.presentation.bot.message_batch.batch_processor.mirror_post_messages",
                new=mirror,
            ),
        ):
            await process_project_create_message_batch(
                batch=batch,
                state=state,
                user=user,
                resolve_channels=MagicMock(),
                config=MagicMock(),
                inline=MagicMock(),
                bot=bot,
            )

        mirror.assert_not_awaited()

    asyncio.run(_run())


def test_create_post_skips_mirror_in_copy_mode() -> None:
    async def _run() -> None:
        _install_fake_project_create_handlers()
        from advertiser_blogger.presentation.bot.common.project_create_draft import new_draft

        msg = _photo_msg(10)
        batch = MessageBatch(
            chat_id=100,
            messages=[msg],
            created_at=datetime.now(tz=timezone.utc),
        )
        user = SimpleNamespace(id=uuid4(), language="ru")
        draft = new_draft(user=user, telegram_id=42)
        draft.publish_mode = PublishMode.copy
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={})
        state.update_data = AsyncMock()
        bot = MagicMock()
        mirror = AsyncMock(return_value=[999])

        with (
            patch(
                "advertiser_blogger.presentation.bot.message_batch.batch_processor.load_draft",
                new=AsyncMock(return_value=draft),
            ),
            patch(
                "advertiser_blogger.presentation.bot.message_batch.batch_processor.save_draft",
                new=AsyncMock(),
            ) as save_draft,
            patch(
                "advertiser_blogger.presentation.bot.message_batch.batch_processor.mirror_post_messages",
                new=mirror,
            ),
        ):
            await process_project_create_message_batch(
                batch=batch,
                state=state,
                user=user,
                resolve_channels=MagicMock(),
                config=MagicMock(),
                inline=MagicMock(),
                bot=bot,
            )

        mirror.assert_not_awaited()
        saved_draft = save_draft.await_args.args[1]
        assert saved_draft.posts[0].bot_message_ids == []

    asyncio.run(_run())
