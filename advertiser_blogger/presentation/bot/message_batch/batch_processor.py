from __future__ import annotations

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from advertiser_blogger.application.interactors_bot.project_create.models import uses_bot_mirror
from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import (
    ResolveChannelQueries,
)
from advertiser_blogger.domain.record.user.entities import User
from advertiser_blogger.presentation.bot.common.mirror_post_messages import (
    mirror_post_messages,
)
from advertiser_blogger.presentation.bot.common.project_create_draft import (
    ASKED_PROJECT_TZ_KEY,
    PAIRING_WAITING_POST_KEY,
    append_post_from_message,
    load_draft,
    new_draft,
    save_draft,
)
from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard
from advertiser_blogger.presentation.bot.message_batch.models import MessageBatch
from advertiser_blogger.presentation.bot.message_batch.pairing_fsm import (
    PairingActionKind,
    ProjectCreatePairingFSM,
)
from configuration.common import CommonConfig


async def process_project_create_message_batch(
        *,
        batch: MessageBatch,
        state: FSMContext,
        user: User,
        resolve_channels: ResolveChannelQueries,
        config: CommonConfig,
        inline: InlineKeyboard,
        bot: Bot,
) -> None:
    # Local import avoids circular dependency with handlers package.
    from advertiser_blogger.presentation.bot.handlers.user.project_create import (
        _apply_metadata_and_maybe_preview,
        _bind_head_if_awaiting_creative,
        _continue_after_batch,
        _maybe_show_preview_or_ask_tz,
    )

    draft = await load_draft(state)
    if draft is None:
        if not batch.messages or batch.messages[0].from_user is None:
            return
        draft = new_draft(user=user, telegram_id=batch.messages[0].from_user.id)

    fsm = ProjectCreatePairingFSM()
    data = await state.get_data()
    waiting_id = data.get(PAIRING_WAITING_POST_KEY)
    if waiting_id is not None:
        fsm.restore(int(waiting_id))
    last_message: Message | None = batch.messages[-1] if batch.messages else None
    newly_created_post = None

    for message in batch.messages:
        for action in fsm.on_message(message):
            if action.kind is PairingActionKind.IGNORE:
                continue

            if action.kind is PairingActionKind.CREATE_POST:
                draft = await load_draft(state) or draft
                before_ids = {p.local_id for p in draft.posts}
                post = append_post_from_message(draft, action.message)
                if post.local_id not in before_ids:
                    newly_created_post = post
                if not post.bot_message_ids and uses_bot_mirror(draft):
                    post.bot_message_ids = await mirror_post_messages(
                        bot,
                        chat_id=action.message.chat.id,
                        source_message_ids=post.source_message_ids,
                    )
                await state.update_data({ASKED_PROJECT_TZ_KEY: False})
                await save_draft(state, draft)
                continue

            if action.kind is PairingActionKind.BIND_CHANNEL:
                draft = await load_draft(state) or draft
                await _apply_metadata_and_maybe_preview(
                    message=action.message,
                    state=state,
                    user=user,
                    draft=draft,
                    resolve_channels=resolve_channels,
                    config=config,
                    inline=inline,
                    bot=bot,
                    reply_to_message_id=action.bind_to_message_id,
                    show_preview=False,
                )
                continue

            if action.kind is PairingActionKind.APPLY_RICH_METADATA:
                draft = await load_draft(state) or draft
                reply_to = (
                    action.message.reply_to_message.message_id
                    if action.message.reply_to_message is not None
                    else None
                )
                await _apply_metadata_and_maybe_preview(
                    message=action.message,
                    state=state,
                    user=user,
                    draft=draft,
                    resolve_channels=resolve_channels,
                    config=config,
                    inline=inline,
                    bot=bot,
                    reply_to_message_id=reply_to,
                    show_preview=False,
                )

    await state.update_data({PAIRING_WAITING_POST_KEY: fsm.waiting_post_message_id})

    if last_message is None:
        return

    draft = await load_draft(state) or draft
    if newly_created_post is not None:
        target = next(
            (p for p in draft.posts if p.local_id == newly_created_post.local_id),
            None,
        )
        if target is not None:
            bound = await _bind_head_if_awaiting_creative(
                new_post=target,
                newly_created=True,
                state=state,
                draft=draft,
                resolve_channels=resolve_channels,
                config=config,
                message=last_message,
                user=user,
                bot=bot,
            )
            if bound:
                draft = await load_draft(state) or draft
                await _continue_after_batch(
                    message=last_message,
                    state=state,
                    user=user,
                    draft=draft,
                    config=config,
                    inline=inline,
                    bot=bot,
                )
                return
    await _maybe_show_preview_or_ask_tz(
        message=last_message,
        state=state,
        user=user,
        draft=draft,
        config=config,
        inline=inline,
        bot=bot,
    )
