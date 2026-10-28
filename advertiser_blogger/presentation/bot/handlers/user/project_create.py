from __future__ import annotations

from uuid import UUID, uuid4

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from dishka import FromDishka
from dishka.integrations.aiogram import inject

from advertiser_blogger.application.interactors_bot.project_create.create_saved.dto import (
    CreateSavedProjectFromBotDraftInput,
)
from advertiser_blogger.application.interactors_bot.project_create.create_saved.use_case import (
    CreateSavedProjectFromBotDraft,
    DraftValidationError,
)
from advertiser_blogger.application.interactors_bot.project_create.models import (
    ParsedScheduleFragments,
    PublishMode,
    uses_bot_mirror,
)
from advertiser_blogger.presentation.bot.common.mirror_post_messages import (
    delete_bot_mirror_messages,
    mirror_post_messages,
)
from advertiser_blogger.presentation.bot.common.project_create_orphans import (
    create_empty_posts_for_channels,
    fill_orphans_leave_empty,
)
from advertiser_blogger.application.interactors_bot.project_create.parser import (
    looks_like_project_metadata,
    parse_project_reply,
)
from advertiser_blogger.presentation.bot.message_batch.pairing_fsm import (
    is_text_creative_message,
    message_has_media,
)
from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import (
    ResolveChannelQueries,
    collect_used_channels_from_draft,
    collect_used_swaps_from_draft,
    filter_duplicate_channel_refs,
    partition_duplicate_channel_queries,
    resolve_bot_form_schedule,
    resolve_project_schedule,
)
from advertiser_blogger.application.interactors_bot.project_create.schedule_fragments import (
    extract_schedule_from_text,
    try_parse_inline_schedule,
)
from advertiser_blogger.domain.record.user.entities import User
from advertiser_blogger.presentation.bot.common.project_create_draft import (
    ASKED_PROJECT_TZ_KEY,
    MENU_CHANNEL_INDEX_KEY,
    ORPHAN_PROMPT_MESSAGE_ID_KEY,
    CHANNEL_MODE_WAITING_CALLBACK_KEY,
    PC_CHANNELS_PER_PAGE,
    PREVIEW_MESSAGE_ID_KEY,
    PREVIEW_PAGE_KEY,
    all_posts_have_channels,
    append_post_from_message,
    apply_channel_attach,
    can_bind_head_to_new_post,
    channel_mode_preview_action,
    clear_pending_metadata,
    clear_processing_notice,
    decide_channel_attach,
    draft_ready_for_preview,
    ensure_posts_channels_one_to_one,
    find_post_by_source_message_id,
    flat_channels,
    get_channel_by_global_index,
    has_post_waiting_for_channels,
    load_draft,
    new_draft,
    peek_channel_batch,
    peek_pending_channel_choice,
    peek_pending_metadata,
    pop_channel_batch,
    pop_pending_by_reply_to_ids,
    enqueue_channel_batch,
    last_post_with_channels,
    pop_pending_metadata,
    project_create_user_lock,
    remove_post_from_draft,
    replace_post_content_from_message,
    replace_post_content_from_album,
    resolve_target_post,
    save_draft,
    set_batch_awaiting_creative,
    set_channel_mode_waiting_callback,
    stash_pending_by_reply_to,
    stash_pending_metadata,
)
from advertiser_blogger.presentation.bot.common.project_create_texts import (
    build_ask_project_tz,
    build_channel_detail_text,
    build_channel_mode_ask_creative_text,
    build_channel_mode_prompt_text,
    build_confirm_progress_text,
    build_create_order_url,
    build_orphan_prompt_text,
    build_preview_text,
    draft_can_confirm,
    t,
)
from advertiser_blogger.presentation.bot.filters.get_user import GetUserByTelegramId
from advertiser_blogger.presentation.bot.filters.project_create import IsProjectCreateCollectInput
from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard
from advertiser_blogger.presentation.bot.states.project_create import ProjectCreateState
from configuration.common import CommonConfig

ProjectCreateRouter = Router(name="ProjectCreateRouter")
ProjectCreateRouter.message.filter(GetUserByTelegramId())
ProjectCreateRouter.callback_query.filter(GetUserByTelegramId())

BTN_CREATE = "Создать РК"

_PROJECT_CREATE_STATES = (
    ProjectCreateState.choosing_publish_mode,
    ProjectCreateState.awaiting_post,
    ProjectCreateState.awaiting_channels_reply,
    ProjectCreateState.preview,
    ProjectCreateState.channel_menu,
    ProjectCreateState.awaiting_replace,
    ProjectCreateState.awaiting_replace_post,
    ProjectCreateState.awaiting_edit_schedule,
    ProjectCreateState.awaiting_edit_comment,
    ProjectCreateState.confirming,
)

_PROJECT_CREATE_COLLECT_STATES = (
    ProjectCreateState.awaiting_post,
    ProjectCreateState.awaiting_channels_reply,
    ProjectCreateState.preview,
    ProjectCreateState.channel_menu,
)


async def _sync_bot_mirror(
        bot: Bot,
        draft,
        post,
        *,
        chat_id: int,
        old_bot_ids: list[int] | None = None,
) -> None:
    if old_bot_ids:
        await delete_bot_mirror_messages(
            bot, chat_id=chat_id, bot_message_ids=old_bot_ids,
        )
    if uses_bot_mirror(draft):
        post.bot_message_ids = await mirror_post_messages(
            bot,
            chat_id=chat_id,
            source_message_ids=post.source_message_ids,
        )
    else:
        post.bot_message_ids = []


@ProjectCreateRouter.message(F.text == BTN_CREATE)
@inject
async def start_project_create(
        message: Message,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
) -> None:
    async with project_create_user_lock(message.from_user.id):
        draft = new_draft(user=user, telegram_id=message.from_user.id)
        await save_draft(state, draft)
        await clear_pending_metadata(state)
        await state.update_data({ASKED_PROJECT_TZ_KEY: False})
        await state.set_state(ProjectCreateState.choosing_publish_mode)
    await message.answer(
        t(user.language, "entry_choose_mode"),
        reply_markup=inline.project_create_mode_choice(
            copy_text=t(user.language, "mode_copy"),
            forward_text=t(user.language, "mode_forward"),
        ),
    )


@ProjectCreateRouter.message(StateFilter(*_PROJECT_CREATE_STATES), F.text == "Отмена")
@inject
async def cancel_project_create(message: Message, state: FSMContext, user: User) -> None:
    async with project_create_user_lock(message.from_user.id):
        await clear_pending_metadata(state)
        await state.clear()
    await message.answer(t(user.language, "cancel"))


@ProjectCreateRouter.callback_query(
    ProjectCreateState.choosing_publish_mode,
    F.data.in_({"pc_mode_copy", "pc_mode_forward"}),
)
@inject
async def choose_publish_mode(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
) -> None:
    mode = PublishMode.copy if callback.data == "pc_mode_copy" else PublishMode.forward
    async with project_create_user_lock(callback.from_user.id):
        draft = await load_draft(state)
        if draft is None:
            draft = new_draft(user=user, telegram_id=callback.from_user.id)
        draft.publish_mode = mode
        await save_draft(state, draft)
        await state.set_state(ProjectCreateState.awaiting_post)
    try:
        await callback.message.edit_text(
            text=t(user.language, "entry"),
            reply_markup=inline.project_create_entry(),
        )
    except TelegramBadRequest:
        await callback.message.answer(
            t(user.language, "entry"),
            reply_markup=inline.project_create_entry(),
        )
    await callback.answer()


@ProjectCreateRouter.message(StateFilter(*_PROJECT_CREATE_COLLECT_STATES), IsProjectCreateCollectInput())
@inject
async def receive_collect(
        message: Message,
        state: FSMContext,
        user: User,
        resolve_channels: FromDishka[ResolveChannelQueries],
        config: FromDishka[CommonConfig],
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    async with project_create_user_lock(message.from_user.id):
        await _receive_collect_locked(
            message=message,
            state=state,
            user=user,
            resolve_channels=resolve_channels,
            config=config,
            inline=inline,
            bot=bot,
        )


async def _receive_collect_locked(
        *,
        message: Message,
        state: FSMContext,
        user: User,
        resolve_channels: ResolveChannelQueries,
        config: CommonConfig,
        inline: InlineKeyboard,
        bot: Bot,
) -> None:
    draft = await load_draft(state)
    if draft is None:
        draft = new_draft(user=user, telegram_id=message.from_user.id)

    text = message.text or message.caption or ""
    reply_to_id = message.reply_to_message.message_id if message.reply_to_message else None
    # Media and special text creatives (button / repost / plain text) are not metadata.
    has_media = message_has_media(message)
    is_creative_text = (not has_media) and is_text_creative_message(text)
    is_meta = (not has_media) and (not is_creative_text) and looks_like_project_metadata(text)

    if not message.media_group_id and is_meta:
        draft = await load_draft(state) or draft
        if reply_to_id is not None and find_post_by_source_message_id(draft, reply_to_id) is None:
            await stash_pending_by_reply_to(state, reply_to_id, text)
            return
        if not draft.posts:
            await stash_pending_metadata(state, text)
            await clear_processing_notice(state)
            await _show_orphan_prompt(
                message=message,
                state=state,
                user=user,
                draft=draft,
                inline=inline,
                bot=bot,
                force_need_creative=True,
            )
            return
        await _apply_metadata_and_maybe_preview(
            message=message,
            state=state,
            user=user,
            draft=draft,
            resolve_channels=resolve_channels,
            config=config,
            inline=inline,
            bot=bot,
            reply_to_message_id=reply_to_id,
        )
        return

    if not message.media_group_id and message.reply_to_message is not None and not is_meta:
        if not draft.posts:
            await message.answer(t(user.language, "need_post_and_data"))
            return
        return

    created_or_updated_ids: list[int] = []
    newly_created_post = None
    if message.media_group_id:
        existing = None
        for p in draft.posts:
            if p.media_group_id == message.media_group_id:
                existing = p
                break
        if existing is None:
            post = append_post_from_message(draft, message)
            newly_created_post = post
            created_or_updated_ids = list(post.source_message_ids)
            await state.update_data({ASKED_PROJECT_TZ_KEY: False})
        else:
            from advertiser_blogger.presentation.bot.common.project_create_draft import message_to_media_parts
            if message.message_id not in existing.source_message_ids:
                existing.media.extend(message_to_media_parts(message))
                existing.source_message_ids.append(message.message_id)
            if message.caption and not existing.text:
                existing.text = message.caption
            draft.active_post_id = existing.local_id
            created_or_updated_ids = list(existing.source_message_ids)
            if not existing.channels:
                await state.update_data({ASKED_PROJECT_TZ_KEY: False})
    else:
        before_ids = {p.local_id for p in draft.posts}
        post = append_post_from_message(draft, message)
        if post.local_id not in before_ids:
            newly_created_post = post
        await _sync_bot_mirror(bot, draft, post, chat_id=message.chat.id)
        created_or_updated_ids = list(post.source_message_ids)
        await state.update_data({ASKED_PROJECT_TZ_KEY: False})
    await save_draft(state, draft)

    pending_by_reply = await pop_pending_by_reply_to_ids(state, created_or_updated_ids)
    if pending_by_reply:
        for reply_mid, pending_text in pending_by_reply:
            await _apply_metadata_and_maybe_preview(
                message=message,
                state=state,
                user=user,
                draft=draft,
                resolve_channels=resolve_channels,
                config=config,
                inline=inline,
                bot=bot,
                metadata_text=pending_text,
                reply_to_message_id=reply_mid,
                show_preview=False,
            )
            draft = await load_draft(state) or draft

    while has_post_waiting_for_channels(draft) and await peek_pending_metadata(state):
        pending = await pop_pending_metadata(state)
        if not pending:
            break
        await _apply_metadata_and_maybe_preview(
            message=message,
            state=state,
            user=user,
            draft=draft,
            resolve_channels=resolve_channels,
            config=config,
            inline=inline,
            bot=bot,
            metadata_text=pending,
            reply_to_message_id=None,
            show_preview=False,
        )
        draft = await load_draft(state) or draft

    if newly_created_post is not None:
        bound = await _bind_head_if_awaiting_creative(
            new_post=newly_created_post,
            newly_created=True,
            state=state,
            draft=draft,
            resolve_channels=resolve_channels,
            config=config,
            message=message,
            user=user,
            bot=bot,
        )
        if bound:
            draft = await load_draft(state) or draft
            await _continue_after_batch(
                message=message,
                state=state,
                user=user,
                draft=draft,
                config=config,
                inline=inline,
                bot=bot,
            )
            return

    await _maybe_show_preview_or_ask_tz(
        message=message,
        state=state,
        user=user,
        draft=draft,
        config=config,
        inline=inline,
        bot=bot,
    )


async def _notify_duplicate_channels(
        message: Message,
        user: User,
        labels: list[str],
) -> None:
    for label in labels:
        text = (label or "").strip()
        if text:
            await message.answer(t(user.language, "duplicate_channel", label=text))


async def _apply_metadata_and_maybe_preview(
        *,
        message: Message,
        state: FSMContext,
        user: User,
        draft,
        resolve_channels: ResolveChannelQueries,
        config: CommonConfig,
        inline: InlineKeyboard,
        bot: Bot,
        metadata_text: str | None = None,
        reply_to_message_id: int | None = None,
        show_preview: bool = True,
) -> None:
    text = metadata_text if metadata_text is not None else (message.text or message.caption or "")
    if reply_to_message_id is None and message.reply_to_message is not None:
        reply_to_message_id = message.reply_to_message.message_id

    draft = await load_draft(state) or draft

    if reply_to_message_id is not None and find_post_by_source_message_id(draft, reply_to_message_id) is None:
        await stash_pending_by_reply_to(state, reply_to_message_id, text)
        return

    parsed = parse_project_reply(text)
    if parsed.project_name:
        draft.project_name = parsed.project_name
    if parsed.comment:
        draft.comment = parsed.comment

    schedule_fr = parsed.schedule
    has_user_schedule = bool(
        schedule_fr.date or schedule_fr.start_time or schedule_fr.end_time or schedule_fr.relative_day
    )
    if has_user_schedule:
        schedule = resolve_bot_form_schedule(
            parsed.schedule,
            timezone=config.bot_project.timezone,
            default_duration_hours=config.bot_project.default_duration_hours,
            slot_minutes=config.bot_project.slot_minutes,
        )
        draft.start_at = schedule.start_at
        draft.end_at = schedule.end_at
        draft.schedule_source = schedule.source

    if parsed.channel_queries:
        stash_text = (metadata_text if metadata_text is not None else (
            message.text or message.caption or ""
        )).strip()
        can_bind = (
            reply_to_message_id is not None
            or has_post_waiting_for_channels(draft)
        )
        target = (
            resolve_target_post(draft, reply_to_message_id=reply_to_message_id)
            if can_bind
            else None
        )
        if target is None:
            if stash_text:
                await save_draft(state, draft)
                if not draft.posts:
                    await stash_pending_metadata(state, stash_text)
                    if show_preview:
                        await clear_processing_notice(state)
                        await state.set_state(ProjectCreateState.awaiting_post)
                        await _show_orphan_prompt(
                            message=message,
                            state=state,
                            user=user,
                            draft=draft,
                            inline=inline,
                            bot=bot,
                            force_need_creative=True,
                        )
                    return
                anchor = last_post_with_channels(draft) or draft.posts[-1]
                await enqueue_channel_batch(
                    state, text=stash_text, anchor_post_id=anchor.local_id,
                )
                if show_preview:
                    await _maybe_show_preview_or_ask_tz(
                        message=message,
                        state=state,
                        user=user,
                        draft=draft,
                        config=config,
                        inline=inline,
                        bot=bot,
                    )
            return
        exclude_urls, exclude_ids = collect_used_swaps_from_draft(
            draft,
            skip_post_id=target.local_id,
        )
        existing_channel_ids, existing_channel_keys = collect_used_channels_from_draft(
            draft,
            skip_post_id=target.local_id,
        )
        had_channels = bool(target.channels)
        unique_queries, dup_query_labels = partition_duplicate_channel_queries(
            parsed.channel_queries,
            existing_channel_ids,
            existing_channel_keys,
        )
        await _notify_duplicate_channels(message, user, dup_query_labels)
        accepted = []
        if unique_queries:
            resolved = await resolve_channels.resolve_many(
                unique_queries,
                timezone=config.bot_project.timezone,
                default_duration_hours=config.bot_project.default_duration_hours,
                slot_minutes=config.bot_project.slot_minutes,
                exclude_swap_urls=exclude_urls,
                exclude_swap_ids=exclude_ids,
            )
            accepted, dup_ref_labels = filter_duplicate_channel_refs(
                resolved,
                existing_channel_ids,
                existing_channel_keys,
            )
            await _notify_duplicate_channels(message, user, dup_ref_labels)

        mode = decide_channel_attach(draft, target, accepted)
        attached = apply_channel_attach(draft, target, accepted, mode)
        target_after = next((p for p in draft.posts if p.local_id == target.local_id), None)
        if not had_channels and (target_after is None or not target_after.channels):
            if target_after is not None:
                remove_post_from_draft(draft, target.local_id)

    await save_draft(state, draft)
    if show_preview:
        await _maybe_show_preview_or_ask_tz(
            message=message,
            state=state,
            user=user,
            draft=draft,
            config=config,
            inline=inline,
            bot=bot,
        )


async def _maybe_show_preview_or_ask_tz(
        *,
        message: Message,
        state: FSMContext,
        user: User,
        draft,
        config: CommonConfig,
        inline: InlineKeyboard,
        bot: Bot,
) -> None:

    gate = await channel_mode_preview_action(state)
    if gate == "return":
        return
    if gate == "show":
        await clear_processing_notice(state)
        await _show_channel_mode_prompt(
            message=message,
            state=state,
            user=user,
            draft=draft,
            inline=inline,
            bot=bot,
        )
        return

    need_channels = has_post_waiting_for_channels(draft)
    need_creative = await peek_pending_metadata(state)
    if need_channels or need_creative:
        await state.set_state(ProjectCreateState.awaiting_post)
        await clear_processing_notice(state)
        await _show_orphan_prompt(
            message=message,
            state=state,
            user=user,
            draft=draft,
            inline=inline,
            bot=bot,
        )
        return

    if all_posts_have_channels(draft) and (draft.start_at is None or draft.end_at is None):
        schedule = resolve_project_schedule(
            None,
            timezone=config.bot_project.timezone,
            default_duration_hours=config.bot_project.default_duration_hours,
            slot_minutes=config.bot_project.slot_minutes,
        )
        draft.start_at = schedule.start_at
        draft.end_at = schedule.end_at
        draft.schedule_source = schedule.source
        await save_draft(state, draft)

    if draft_ready_for_preview(draft):
        ensure_posts_channels_one_to_one(draft)
        await save_draft(state, draft)
        await clear_processing_notice(state)
        await _clear_orphan_prompt(bot=bot, state=state, chat_id=message.chat.id)
        await state.update_data({ASKED_PROJECT_TZ_KEY: False})
        await state.set_state(ProjectCreateState.preview)
        await _show_preview(
            bot=bot,
            state=state,
            chat_id=message.chat.id,
            draft=draft,
            user=user,
            inline=inline,
            prefer_answer_to=message,
        )
        return

    await state.set_state(ProjectCreateState.awaiting_post)
    await clear_processing_notice(state)

    if draft.posts and not has_post_waiting_for_channels(draft):
        ask_tz = build_ask_project_tz(draft, user.language)
        if ask_tz:
            await message.answer(ask_tz)


async def _bind_head_if_awaiting_creative(
        *,
        new_post,
        newly_created: bool,
        state: FSMContext,
        draft,
        resolve_channels: ResolveChannelQueries,
        config: CommonConfig,
        message: Message,
        user: User,
        bot: Bot,
) -> bool:
    """Attach HEAD to this ingest's new post only when HEAD.awaiting_creative."""
    draft = await load_draft(state) or draft
    target = next((p for p in draft.posts if p.local_id == new_post.local_id), None)
    head = await peek_channel_batch(state)
    if not can_bind_head_to_new_post(head, target, newly_created=newly_created):
        return False
    accepted = await _resolve_channels_from_text(
        text=head["text"],
        draft=draft,
        resolve_channels=resolve_channels,
        config=config,
        skip_post_id=target.local_id,
        message=message,
        user=user,
    )
    if not accepted:
        return False
    popped = await pop_channel_batch(state)
    if popped is None:
        return False
    apply_channel_attach(draft, target, accepted, "attach")
    await save_draft(state, draft)
    await _clear_orphan_prompt(
        bot=bot,
        state=state,
        chat_id=message.chat.id,
    )
    return True


# Backward-compatible name used by album flush_handler.
_apply_metadata_and_show_preview = _apply_metadata_and_maybe_preview


async def _clear_orphan_prompt(
        *,
        bot: Bot,
        state: FSMContext,
        chat_id: int,
) -> None:
    data = await state.get_data()
    prompt_id = data.get(ORPHAN_PROMPT_MESSAGE_ID_KEY)
    await state.update_data({
        ORPHAN_PROMPT_MESSAGE_ID_KEY: None,
        CHANNEL_MODE_WAITING_CALLBACK_KEY: None,
    })
    if prompt_id is None:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(prompt_id))
    except TelegramBadRequest:
        pass


async def _show_orphan_prompt(
        *,
        message: Message,
        state: FSMContext,
        user: User,
        draft,
        inline: InlineKeyboard,
        bot: Bot,
        force_need_creative: bool = False,
) -> None:
    need_channels = has_post_waiting_for_channels(draft)
    need_creative = force_need_creative or await peek_pending_metadata(state)
    text = build_orphan_prompt_text(
        user.language,
        need_channels=need_channels,
        need_creative=need_creative,
    )
    if not text:
        return
    data = await state.get_data()
    existing_id = data.get(ORPHAN_PROMPT_MESSAGE_ID_KEY)
    reply_markup = inline.project_create_orphan_leave_empty(
        button_text=t(user.language, "orphan_leave_empty"),
    )
    if existing_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=int(existing_id),
                text=text,
                reply_markup=reply_markup,
            )
            return
        except TelegramBadRequest:
            await state.update_data({ORPHAN_PROMPT_MESSAGE_ID_KEY: None})
    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data({ORPHAN_PROMPT_MESSAGE_ID_KEY: sent.message_id})


@ProjectCreateRouter.callback_query(
    StateFilter(*_PROJECT_CREATE_STATES),
    F.data == "pc_orphan_leave_empty",
)
@inject
async def orphan_leave_empty_cb(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        resolve_channels: FromDishka[ResolveChannelQueries],
        config: FromDishka[CommonConfig],
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    async with project_create_user_lock(callback.from_user.id):
        draft = await load_draft(state)
        if draft is None:
            await callback.answer()
            return
        filled = await fill_orphans_leave_empty(
            state=state,
            draft=draft,
            resolve_channels=resolve_channels,
            config=config,
        )
        draft = await load_draft(state) or draft
        await _clear_orphan_prompt(
            bot=bot,
            state=state,
            chat_id=callback.message.chat.id,
        )
        if not filled:
            await callback.answer(t(user.language, "orphan_leave_empty_failed"), show_alert=True)
            await _show_orphan_prompt(
                message=callback.message,
                state=state,
                user=user,
                draft=draft,
                inline=inline,
                bot=bot,
            )
            return
        await callback.answer(t(user.language, "orphan_leave_empty_ok"))
        await _maybe_show_preview_or_ask_tz(
            message=callback.message,
            state=state,
            user=user,
            draft=draft,
            config=config,
            inline=inline,
            bot=bot,
        )


async def _show_channel_mode_prompt(
        *,
        message: Message,
        state: FSMContext,
        user: User,
        draft,
        inline: InlineKeyboard,
        bot: Bot,
) -> None:
    batch = await peek_channel_batch(state)
    text = build_channel_mode_prompt_text(user.language, batch["text"] if batch else "")
    reply_markup = inline.project_create_channel_mode_choice(
        to_above_text=t(user.language, "channel_mode_to_above"),
        own_creative_text=t(user.language, "channel_mode_own_creative"),
        leave_empty_text=t(user.language, "channel_mode_leave_empty"),
    )
    data = await state.get_data()
    existing_id = data.get(ORPHAN_PROMPT_MESSAGE_ID_KEY)
    if existing_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=int(existing_id),
                text=text,
                reply_markup=reply_markup,
            )
            await set_channel_mode_waiting_callback(state, True)
            return
        except TelegramBadRequest:
            await state.update_data({ORPHAN_PROMPT_MESSAGE_ID_KEY: None})
    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data({ORPHAN_PROMPT_MESSAGE_ID_KEY: sent.message_id})
    await set_channel_mode_waiting_callback(state, True)


async def _continue_after_batch(
        *,
        message: Message,
        state: FSMContext,
        user: User,
        draft,
        config: CommonConfig,
        inline: InlineKeyboard,
        bot: Bot,
) -> None:
    """Show next orphan-batch SMS or fall through to preview/TZ."""
    if await peek_pending_channel_choice(state):
        await _show_channel_mode_prompt(
            message=message,
            state=state,
            user=user,
            draft=draft,
            inline=inline,
            bot=bot,
        )
        return
    await _maybe_show_preview_or_ask_tz(
        message=message,
        state=state,
        user=user,
        draft=draft,
        config=config,
        inline=inline,
        bot=bot,
    )


async def _resolve_channels_from_text(
        *,
        text: str,
        draft,
        resolve_channels: ResolveChannelQueries,
        config: CommonConfig,
        skip_post_id: str | None = None,
        message: Message | None = None,
        user: User | None = None,
) -> list:
    parsed = parse_project_reply(text)
    if not parsed.channel_queries:
        return []
    exclude_urls, exclude_ids = collect_used_swaps_from_draft(
        draft,
        skip_post_id=skip_post_id,
    )
    existing_channel_ids, existing_channel_keys = collect_used_channels_from_draft(
        draft,
        skip_post_id=skip_post_id,
    )
    unique_queries, dup_query_labels = partition_duplicate_channel_queries(
        parsed.channel_queries,
        existing_channel_ids,
        existing_channel_keys,
    )
    if message is not None and user is not None:
        await _notify_duplicate_channels(message, user, dup_query_labels)
    if not unique_queries:
        return []
    resolved = await resolve_channels.resolve_many(
        unique_queries,
        timezone=config.bot_project.timezone,
        default_duration_hours=config.bot_project.default_duration_hours,
        slot_minutes=config.bot_project.slot_minutes,
        exclude_swap_urls=exclude_urls,
        exclude_swap_ids=exclude_ids,
    )
    accepted, dup_ref_labels = filter_duplicate_channel_refs(
        resolved,
        existing_channel_ids,
        existing_channel_keys,
    )
    if message is not None and user is not None:
        await _notify_duplicate_channels(message, user, dup_ref_labels)
    return accepted


@ProjectCreateRouter.callback_query(
    StateFilter(*_PROJECT_CREATE_STATES),
    F.data == "pc_to_above",
)
@inject
async def channel_to_above_cb(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        resolve_channels: FromDishka[ResolveChannelQueries],
        config: FromDishka[CommonConfig],
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    async with project_create_user_lock(callback.from_user.id):
        draft = await load_draft(state)
        batch = await pop_channel_batch(state)
        if draft is None or batch is None:
            await callback.answer(t(user.language, "channel_mode_failed"), show_alert=True)
            return
        anchor_id = batch.get("anchor_post_id")
        target = next((p for p in draft.posts if p.local_id == anchor_id), None)
        if target is None:
            await callback.answer(t(user.language, "channel_mode_failed"), show_alert=True)
            return
        accepted = await _resolve_channels_from_text(
            text=batch["text"],
            draft=draft,
            resolve_channels=resolve_channels,
            config=config,
            skip_post_id=target.local_id,
            message=callback.message,
            user=user,
        )
        await _clear_orphan_prompt(
            bot=bot,
            state=state,
            chat_id=callback.message.chat.id,
        )
        if not accepted:
            await callback.answer(t(user.language, "channel_mode_failed"), show_alert=True)
            await save_draft(state, draft)
            return
        apply_channel_attach(draft, target, accepted, "attach")
        await save_draft(state, draft)
        await callback.answer(t(user.language, "channel_mode_ok_above"))
        await _continue_after_batch(
            message=callback.message,
            state=state,
            user=user,
            draft=draft,
            config=config,
            inline=inline,
            bot=bot,
        )


@ProjectCreateRouter.callback_query(
    StateFilter(*_PROJECT_CREATE_STATES),
    F.data == "pc_batch_creative",
)
@inject
async def channel_batch_creative_cb(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    async with project_create_user_lock(callback.from_user.id):
        if not await peek_pending_channel_choice(state):
            await callback.answer(t(user.language, "channel_mode_failed"), show_alert=True)
            return
        ok = await set_batch_awaiting_creative(state)
        if not ok:
            await callback.answer(t(user.language, "channel_mode_failed"), show_alert=True)
            return
        await _clear_orphan_prompt(
            bot=bot,
            state=state,
            chat_id=callback.message.chat.id,
        )
        await state.set_state(ProjectCreateState.awaiting_post)
        batch = await peek_channel_batch(state)
        sent = await callback.message.answer(
            build_channel_mode_ask_creative_text(
                user.language,
                batch["text"] if batch else "",
            ),
        )
        await state.update_data({ORPHAN_PROMPT_MESSAGE_ID_KEY: sent.message_id})
        await callback.answer()


@ProjectCreateRouter.callback_query(
    StateFilter(*_PROJECT_CREATE_STATES),
    F.data == "pc_channel_leave_empty",
)
@inject
async def channel_leave_empty_cb(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        resolve_channels: FromDishka[ResolveChannelQueries],
        config: FromDishka[CommonConfig],
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    async with project_create_user_lock(callback.from_user.id):
        draft = await load_draft(state)
        batch = await pop_channel_batch(state)
        if draft is None or batch is None:
            await callback.answer(t(user.language, "channel_mode_failed"), show_alert=True)
            return
        accepted = await _resolve_channels_from_text(
            text=batch["text"],
            draft=draft,
            resolve_channels=resolve_channels,
            config=config,
            message=callback.message,
            user=user,
        )
        await _clear_orphan_prompt(
            bot=bot,
            state=state,
            chat_id=callback.message.chat.id,
        )
        if not accepted:
            await callback.answer(t(user.language, "channel_mode_failed"), show_alert=True)
            await save_draft(state, draft)
            return
        create_empty_posts_for_channels(draft, accepted)
        await save_draft(state, draft)
        await callback.answer(t(user.language, "channel_mode_ok_empty"))
        await _continue_after_batch(
            message=callback.message,
            state=state,
            user=user,
            draft=draft,
            config=config,
            inline=inline,
            bot=bot,
        )


@ProjectCreateRouter.callback_query(StateFilter(*_PROJECT_CREATE_STATES), F.data == "pc_cancel")
@inject
async def cancel_cb(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
) -> None:
    async with project_create_user_lock(callback.from_user.id):
        await clear_pending_metadata(state)
        await state.clear()
    try:
        await callback.message.edit_text(
            text=t(user.language, "cancel"),
            reply_markup=None,
        )
    except TelegramBadRequest:
        await callback.message.answer(t(user.language, "cancel"))
    await callback.answer()


@ProjectCreateRouter.callback_query(ProjectCreateState.preview, F.data.startswith("pc_page:"))
@inject
async def preview_change_page(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    page = int(callback.data.split(":")[1])
    await state.update_data({PREVIEW_PAGE_KEY: page})
    draft = await load_draft(state)
    if draft is None:
        await callback.answer()
        return
    await _show_preview(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        fallback_message=callback.message,
    )
    await callback.answer()


@ProjectCreateRouter.callback_query(ProjectCreateState.preview, F.data == "pc_page_noop")
@inject
async def preview_page_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@ProjectCreateRouter.callback_query(ProjectCreateState.preview, F.data.startswith("pc_ch:"))
@inject
async def open_channel_menu(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    if draft is None:
        await callback.answer()
        return
    idx = int(callback.data.split(":")[1])
    item = get_channel_by_global_index(draft, idx)
    if item is None:
        await callback.answer()
        return
    await state.update_data({MENU_CHANNEL_INDEX_KEY: idx})
    await _show_channel_detail(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        channel_index=idx,
        fallback_message=callback.message,
    )
    await callback.answer()


@ProjectCreateRouter.callback_query(ProjectCreateState.channel_menu, F.data == "pc_back")
@ProjectCreateRouter.callback_query(ProjectCreateState.preview, F.data == "pc_back")
@inject
async def back_to_preview(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    if draft is None:
        await callback.answer()
        return
    await state.set_state(ProjectCreateState.preview)
    await _show_preview(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        fallback_message=callback.message,
    )
    await callback.answer()


@ProjectCreateRouter.callback_query(
    StateFilter(
        ProjectCreateState.awaiting_replace,
        ProjectCreateState.awaiting_replace_post,
        ProjectCreateState.awaiting_edit_schedule,
        ProjectCreateState.awaiting_edit_comment,
    ),
    F.data.in_({"pc_back_channel", "pc_back"}),
)
@inject
async def back_to_channel_menu(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    data = await state.get_data()
    idx = int(data.get(MENU_CHANNEL_INDEX_KEY) or 0)
    if draft is None or idx < 1 or get_channel_by_global_index(draft, idx) is None:
        if draft is not None:
            await state.set_state(ProjectCreateState.preview)
            await _show_preview(
                bot=bot,
                state=state,
                chat_id=callback.message.chat.id,
                draft=draft,
                user=user,
                inline=inline,
                fallback_message=callback.message,
            )
        await callback.answer()
        return
    await _show_channel_detail(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        channel_index=idx,
        fallback_message=callback.message,
    )
    await callback.answer()


@ProjectCreateRouter.callback_query(ProjectCreateState.channel_menu, F.data.startswith("pc_delete:"))
@inject
async def delete_channel(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    if draft is None:
        await callback.answer()
        return
    idx = int(callback.data.split(":")[1])
    item = get_channel_by_global_index(draft, idx)
    if item is not None:
        post_id, local_idx, _ = item
        for post in draft.posts:
            if post.local_id == post_id:
                post.channels.pop(local_idx)
                if not post.channels:
                    remove_post_from_draft(draft, post_id)
                break
        await save_draft(state, draft)
    await state.set_state(ProjectCreateState.preview)
    await _show_preview(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        fallback_message=callback.message,
    )
    await callback.answer()


@ProjectCreateRouter.callback_query(ProjectCreateState.channel_menu, F.data.startswith("pc_show_post:"))
@inject
async def show_channel_post(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    if draft is None:
        await callback.answer()
        return
    idx = int(callback.data.split(":")[1])
    item = get_channel_by_global_index(draft, idx)
    if item is None:
        await callback.answer()
        return
    post_id, _, _ = item
    post = next((p for p in draft.posts if p.local_id == post_id), None)
    if post is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    try:
        ids = sorted(set(post.bot_message_ids or post.source_message_ids or []))
        if ids:
            if len(ids) == 1:
                await bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=chat_id,
                    message_id=ids[0],
                )
            else:
                await bot.copy_messages(
                    chat_id=chat_id,
                    from_chat_id=chat_id,
                    message_ids=ids,
                )
        elif post.text:
            await bot.send_message(chat_id=chat_id, text=post.text)
        else:
            await callback.answer(t(user.language, "show_post_empty"), show_alert=True)
            return
    except Exception:
        await callback.answer(t(user.language, "show_post_failed"), show_alert=True)
        return
    await callback.answer()


@ProjectCreateRouter.callback_query(ProjectCreateState.channel_menu, F.data.startswith("pc_replace_post:"))
@inject
async def replace_post_prompt(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    idx = int(callback.data.split(":")[1])
    await state.update_data({MENU_CHANNEL_INDEX_KEY: idx})
    await state.set_state(ProjectCreateState.awaiting_replace_post)
    await _edit_ui_message(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        text=t(user.language, "replace_post_prompt"),
        reply_markup=inline.project_create_back_to_channel(),
        fallback_message=callback.message,
    )
    await callback.answer()


@ProjectCreateRouter.callback_query(ProjectCreateState.channel_menu, F.data.startswith("pc_reset_time:"))
@inject
async def reset_channel_schedule(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    if draft is None:
        await callback.answer()
        return
    idx = int(callback.data.split(":")[1])
    item = get_channel_by_global_index(draft, idx)
    if item is not None:
        post_id, local_idx, ch = item
        ch.start_at = None
        ch.end_at = None
        ch.schedule_source = None
        for post in draft.posts:
            if post.local_id == post_id:
                post.channels[local_idx] = ch
                break
        await save_draft(state, draft)
    await _show_channel_detail(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        channel_index=idx,
        fallback_message=callback.message,
    )
    await callback.answer(t(user.language, "reset_schedule_ok"))


@ProjectCreateRouter.callback_query(ProjectCreateState.channel_menu, F.data.startswith("pc_reset_comment:"))
@inject
async def reset_channel_comment(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    if draft is None:
        await callback.answer()
        return
    idx = int(callback.data.split(":")[1])
    item = get_channel_by_global_index(draft, idx)
    if item is not None:
        post_id, local_idx, ch = item
        if ch.comment and str(ch.comment).strip():
            ch.comment = None
        elif ch.comment is None:
            ch.comment = ""
        for post in draft.posts:
            if post.local_id == post_id:
                post.channels[local_idx] = ch
                break
        await save_draft(state, draft)
    await _show_channel_detail(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        channel_index=idx,
        fallback_message=callback.message,
    )
    await callback.answer(t(user.language, "reset_comment_ok"))


@ProjectCreateRouter.callback_query(ProjectCreateState.channel_menu, F.data.startswith("pc_edit_time:"))
@inject
async def edit_channel_schedule_prompt(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    idx = int(callback.data.split(":")[1])
    await state.update_data({MENU_CHANNEL_INDEX_KEY: idx})
    await state.set_state(ProjectCreateState.awaiting_edit_schedule)
    await _edit_ui_message(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        text=t(user.language, "edit_schedule_prompt"),
        reply_markup=inline.project_create_back_to_channel(),
        fallback_message=callback.message,
    )
    await callback.answer()


@ProjectCreateRouter.callback_query(ProjectCreateState.channel_menu, F.data.startswith("pc_edit_comment:"))
@inject
async def edit_channel_comment_prompt(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    idx = int(callback.data.split(":")[1])
    await state.update_data({MENU_CHANNEL_INDEX_KEY: idx})
    await state.set_state(ProjectCreateState.awaiting_edit_comment)
    await _edit_ui_message(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        text=t(user.language, "edit_comment_prompt"),
        reply_markup=inline.project_create_back_to_channel(),
        fallback_message=callback.message,
    )
    await callback.answer()


@ProjectCreateRouter.callback_query(ProjectCreateState.channel_menu, F.data.startswith("pc_replace:"))
@inject
async def replace_channel_prompt(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    idx = int(callback.data.split(":")[1])
    await state.update_data({MENU_CHANNEL_INDEX_KEY: idx})
    await state.set_state(ProjectCreateState.awaiting_replace)
    await _edit_ui_message(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        text=t(user.language, "replace_prompt"),
        reply_markup=inline.project_create_back_to_channel(),
        fallback_message=callback.message,
    )
    await callback.answer()


@ProjectCreateRouter.message(ProjectCreateState.awaiting_edit_schedule, IsProjectCreateCollectInput())
@inject
async def edit_channel_schedule_value(
        message: Message,
        state: FSMContext,
        user: User,
        config: FromDishka[CommonConfig],
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    data = await state.get_data()
    idx = int(data.get(MENU_CHANNEL_INDEX_KEY) or 0)
    if draft is None or idx < 1:
        await state.set_state(ProjectCreateState.preview)
        return
    item = get_channel_by_global_index(draft, idx)
    if item is None:
        await state.set_state(ProjectCreateState.preview)
        return

    text = (message.text or message.caption or "").strip()
    fragments = ParsedScheduleFragments()
    if not try_parse_inline_schedule(text, fragments):
        extract_schedule_from_text(text, fragments)
    has_schedule = bool(
        fragments.date
        or fragments.start_time
        or fragments.end_time
        or fragments.relative_day
    )
    if not has_schedule:
        await message.answer(
            t(user.language, "edit_schedule_invalid"),
            reply_markup=inline.project_create_back_to_channel(),
        )
        return
    try:
        schedule = resolve_bot_form_schedule(
            fragments,
            timezone=config.bot_project.timezone,
            default_duration_hours=config.bot_project.default_duration_hours,
            slot_minutes=config.bot_project.slot_minutes,
        )
    except Exception:
        await message.answer(
            t(user.language, "edit_schedule_invalid"),
            reply_markup=inline.project_create_back_to_channel(),
        )
        return

    post_id, local_idx, ch = item
    ch.start_at = schedule.start_at
    ch.end_at = schedule.end_at
    ch.schedule_source = schedule.source
    for post in draft.posts:
        if post.local_id == post_id:
            post.channels[local_idx] = ch
            break
    await save_draft(state, draft)
    await _show_channel_detail(
        bot=bot,
        state=state,
        chat_id=message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        channel_index=idx,
        resend_ui=True,
        answer_to=message,
    )


@ProjectCreateRouter.message(ProjectCreateState.awaiting_edit_comment, IsProjectCreateCollectInput())
@inject
async def edit_channel_comment_value(
        message: Message,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    data = await state.get_data()
    idx = int(data.get(MENU_CHANNEL_INDEX_KEY) or 0)
    if draft is None or idx < 1:
        await state.set_state(ProjectCreateState.preview)
        return
    item = get_channel_by_global_index(draft, idx)
    if item is None:
        await state.set_state(ProjectCreateState.preview)
        return

    comment = (message.text or message.caption or "").strip()
    post_id, local_idx, ch = item
    ch.comment = comment or None
    for post in draft.posts:
        if post.local_id == post_id:
            post.channels[local_idx] = ch
            break
    await save_draft(state, draft)
    await _show_channel_detail(
        bot=bot,
        state=state,
        chat_id=message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        channel_index=idx,
        resend_ui=True,
        answer_to=message,
    )


@ProjectCreateRouter.message(ProjectCreateState.awaiting_replace_post, IsProjectCreateCollectInput())
@inject
async def replace_post_value(
        message: Message,
        state: FSMContext,
        user: User,
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    data = await state.get_data()
    idx = int(data.get(MENU_CHANNEL_INDEX_KEY) or 0)
    if draft is None or idx < 1:
        await state.set_state(ProjectCreateState.preview)
        return
    if message.media_group_id:
        # Album parts are handled by AlbumCollector flush (awaiting_replace_post branch).
        return
    item = get_channel_by_global_index(draft, idx)
    if item is None:
        await state.set_state(ProjectCreateState.preview)
        await _show_preview(
            bot=bot,
            state=state,
            chat_id=message.chat.id,
            draft=draft,
            user=user,
            inline=inline,
        )
        return
    post_id, _, _ = item
    post = next((p for p in draft.posts if p.local_id == post_id), None)
    if post is None:
        await state.set_state(ProjectCreateState.preview)
        return
    old_bot_ids = list(post.bot_message_ids)
    replace_post_content_from_message(post, message)
    await _sync_bot_mirror(
        bot, draft, post, chat_id=message.chat.id, old_bot_ids=old_bot_ids,
    )
    await save_draft(state, draft)
    await _show_channel_detail(
        bot=bot,
        state=state,
        chat_id=message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        channel_index=idx,
        resend_ui=True,
        answer_to=message,
    )


@ProjectCreateRouter.message(ProjectCreateState.awaiting_replace, IsProjectCreateCollectInput())
@inject
async def replace_channel_value(
        message: Message,
        state: FSMContext,
        user: User,
        resolve_channels: FromDishka[ResolveChannelQueries],
        config: FromDishka[CommonConfig],
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
) -> None:
    draft = await load_draft(state)
    data = await state.get_data()
    idx = int(data.get(MENU_CHANNEL_INDEX_KEY) or 0)
    if draft is None or idx < 1:
        await state.set_state(ProjectCreateState.preview)
        return
    item = get_channel_by_global_index(draft, idx)
    exclude_urls: set[str] = set()
    exclude_ids: set[UUID] = set()
    if item is not None:
        post_id, local_idx, _ = item
        exclude_urls, exclude_ids = collect_used_swaps_from_draft(
            draft,
            skip_post_channel=(post_id, local_idx),
        )
    refs = await resolve_channels.resolve_many(
        [message.text or ""],
        timezone=config.bot_project.timezone,
        default_duration_hours=config.bot_project.default_duration_hours,
        slot_minutes=config.bot_project.slot_minutes,
        exclude_swap_urls=exclude_urls,
        exclude_swap_ids=exclude_ids,
    )
    if not refs:
        await message.answer(
            t(user.language, "replace_prompt"),
            reply_markup=inline.project_create_back_to_channel(),
        )
        return
    if item is not None:
        post_id, local_idx, _ = item
        existing_channel_ids, existing_channel_keys = collect_used_channels_from_draft(
            draft,
            skip_post_channel=(post_id, local_idx),
        )
        accepted, dup_labels = filter_duplicate_channel_refs(
            refs,
            existing_channel_ids,
            existing_channel_keys,
        )
        await _notify_duplicate_channels(message, user, dup_labels)
        if not accepted:
            await state.set_state(ProjectCreateState.preview)
            await _show_preview(
                bot=bot,
                state=state,
                chat_id=message.chat.id,
                draft=draft,
                user=user,
                inline=inline,
            )
            return
        for post in draft.posts:
            if post.local_id == post_id:
                post.channels[local_idx] = accepted[0]
                break
    await save_draft(state, draft)
    await state.set_state(ProjectCreateState.preview)
    await _show_preview(
        bot=bot,
        state=state,
        chat_id=message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        resend_ui=True,
        answer_to=message,
    )


@ProjectCreateRouter.callback_query(ProjectCreateState.preview, F.data == "pc_confirm")
@inject
async def confirm_save(
        callback: CallbackQuery,
        state: FSMContext,
        user: User,
        create_saved: FromDishka[CreateSavedProjectFromBotDraft],
        inline: FromDishka[InlineKeyboard],
        bot: FromDishka[Bot],
        config: FromDishka[CommonConfig],
) -> None:
    draft = await load_draft(state)
    if draft is None:
        await callback.answer()
        return

    if not draft_can_confirm(draft):
        await state.set_state(ProjectCreateState.preview)
        await _show_preview(
            bot=bot,
            state=state,
            chat_id=callback.message.chat.id,
            draft=draft,
            user=user,
            inline=inline,
            fallback_message=callback.message,
            banner=t(user.language, "confirm_blocked_unknown"),
        )
        await callback.answer()
        return

    await state.set_state(ProjectCreateState.confirming)
    await callback.answer()

    async def on_progress(phase: str, current: int, total: int) -> None:
        try:
            await _edit_ui_message(
                bot=bot,
                state=state,
                chat_id=callback.message.chat.id,
                text=build_confirm_progress_text(user.language, phase, current, total),
                reply_markup=None,
                fallback_message=callback.message,
            )
        except Exception:
            pass

    try:
        result = await create_saved(
            data=CreateSavedProjectFromBotDraftInput(
                draft=draft,
                user_id=user.id,
                on_progress=on_progress,
            ),
        )
    except DraftValidationError:
        await state.set_state(ProjectCreateState.preview)
        await _show_preview(
            bot=bot,
            state=state,
            chat_id=callback.message.chat.id,
            draft=draft,
            user=user,
            inline=inline,
            fallback_message=callback.message,
            banner=t(user.language, "confirm_blocked_unknown"),
        )
        return
    except Exception:
        await state.set_state(ProjectCreateState.preview)
        await _show_preview(
            bot=bot,
            state=state,
            chat_id=callback.message.chat.id,
            draft=draft,
            user=user,
            inline=inline,
            fallback_message=callback.message,
            banner=t(user.language, "confirm_error"),
        )
        return

    project_url = build_create_order_url(
        frontend_domain=config.bot.frontend_domain,
        project_id=result.project_id,
    )
    text = (
        t(user.language, "confirm_partial", project_url=project_url)
        if result.partial
        else t(user.language, "confirm_ok", project_url=project_url)
    )
    await _edit_ui_message(
        bot=bot,
        state=state,
        chat_id=callback.message.chat.id,
        text=text,
        reply_markup=inline.project_create_saved(project_url=project_url),
        fallback_message=callback.message,
    )
    await state.clear()


async def _show_channel_detail(
        *,
        bot: Bot,
        state: FSMContext,
        chat_id: int,
        draft,
        user: User,
        inline: InlineKeyboard,
        channel_index: int,
        fallback_message: Message | None = None,
        resend_ui: bool = False,
        answer_to: Message | None = None,
) -> None:
    item = get_channel_by_global_index(draft, channel_index)
    if item is None:
        await state.set_state(ProjectCreateState.preview)
        await _show_preview(
            bot=bot,
            state=state,
            chat_id=chat_id,
            draft=draft,
            user=user,
            inline=inline,
            fallback_message=fallback_message,
            resend_ui=resend_ui,
            answer_to=answer_to,
        )
        return
    _, _, ch = item
    await state.update_data({MENU_CHANNEL_INDEX_KEY: channel_index})
    await state.set_state(ProjectCreateState.channel_menu)
    text = build_channel_detail_text(ch, channel_index, draft, user.language)
    reply_markup = inline.project_create_channel_menu(channel_index=channel_index)
    if resend_ui:
        await _resend_ui_message(
            bot=bot,
            state=state,
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            answer_to=answer_to,
        )
        return
    await _edit_ui_message(
        bot=bot,
        state=state,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        fallback_message=fallback_message,
    )


async def _show_preview(
        *,
        bot: Bot,
        state: FSMContext,
        chat_id: int,
        draft,
        user: User,
        inline: InlineKeyboard,
        prefer_answer_to: Message | None = None,
        fallback_message: Message | None = None,
        banner: str | None = None,
        resend_ui: bool = False,
        answer_to: Message | None = None,
) -> None:
    channel_count = len(flat_channels(draft))
    data = await state.get_data()
    if prefer_answer_to is not None or resend_ui:
        page = 1
    else:
        page = int(data.get(PREVIEW_PAGE_KEY) or 1)
    ensure_posts_channels_one_to_one(draft)
    await save_draft(state, draft)
    channel_count = len(flat_channels(draft))
    total_pages = max(1, (channel_count + PC_CHANNELS_PER_PAGE - 1) // PC_CHANNELS_PER_PAGE) if channel_count else 1
    page = max(1, min(page, total_pages))
    await state.update_data({PREVIEW_PAGE_KEY: page})

    text = build_preview_text(
        draft,
        user.language,
        banner=banner,
        page=page,
        page_size=PC_CHANNELS_PER_PAGE,
    )
    reply_markup = inline.project_create_preview(
        channel_count=channel_count,
        page=page,
        confirm_enabled=draft_can_confirm(draft),
        page_size=PC_CHANNELS_PER_PAGE,
    )

    anchor = prefer_answer_to or answer_to
    if prefer_answer_to is not None or resend_ui:
        await _resend_ui_message(
            bot=bot,
            state=state,
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            answer_to=anchor,
        )
        return

    await _edit_ui_message(
        bot=bot,
        state=state,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        fallback_message=fallback_message,
    )


async def _resend_ui_message(
        *,
        bot: Bot,
        state: FSMContext,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None,
        answer_to: Message | None = None,
) -> None:
    """Delete previous bot UI message and send a fresh one (after user input)."""
    data = await state.get_data()
    old_id = data.get(PREVIEW_MESSAGE_ID_KEY)
    if old_id is not None:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=old_id)
        except TelegramBadRequest:
            pass
    if answer_to is not None:
        sent = await answer_to.answer(text, reply_markup=reply_markup)
    else:
        sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    await state.update_data({PREVIEW_MESSAGE_ID_KEY: sent.message_id})


async def _edit_ui_message(
        *,
        bot: Bot,
        state: FSMContext,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None,
        fallback_message: Message | None = None,
) -> None:
    data = await state.get_data()
    message_id = data.get(PREVIEW_MESSAGE_ID_KEY)
    if message_id is None and fallback_message is not None:
        message_id = fallback_message.message_id
        await state.update_data({PREVIEW_MESSAGE_ID_KEY: message_id})

    if message_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return

    if fallback_message is not None:
        try:
            await fallback_message.edit_text(text=text, reply_markup=reply_markup)
            await state.update_data({PREVIEW_MESSAGE_ID_KEY: fallback_message.message_id})
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                await state.update_data({PREVIEW_MESSAGE_ID_KEY: fallback_message.message_id})
                return
            sent = await fallback_message.answer(text, reply_markup=reply_markup)
            await state.update_data({PREVIEW_MESSAGE_ID_KEY: sent.message_id})
            return

    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    await state.update_data({PREVIEW_MESSAGE_ID_KEY: sent.message_id})


@ProjectCreateRouter.callback_query(
    StateFilter(*_PROJECT_CREATE_STATES),
    ~F.data.startswith("pc_"),
)
@inject
async def exit_on_foreign_callback(
        callback: CallbackQuery,
        state: FSMContext,
) -> None:
    async with project_create_user_lock(callback.from_user.id):
        await clear_pending_metadata(state)
        await state.clear()
    await callback.answer()


async def ingest_album_into_draft(state: FSMContext, user: User, aggregated, message: Message):
    """Used by album flush when in ProjectCreateState. Returns newly created post or None."""
    from advertiser_blogger.application.interactors_bot.project_create.models import (
        BotMediaPart,
        BotPostDraft,
    )
    from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import (
        CreativeKind,
    )

    draft = await load_draft(state)
    if draft is None:
        draft = new_draft(user=user, telegram_id=message.from_user.id)

    existing = None
    for p in draft.posts:
        if p.media_group_id and p.media_group_id == aggregated.media_group_id:
            existing = p
            break

    media = [
        BotMediaPart(
            content_type=part.media_type,
            file_id=part.file_id,
            text=part.caption,
        )
        for part in aggregated.parts
    ]
    caption = next((part.caption for part in aggregated.parts if part.caption), None)
    message_ids = [p.message_id for p in aggregated.parts]

    if existing is None:
        post = BotPostDraft(
            local_id=str(uuid4()),
            text=caption,
            media=media,
            source_message_ids=message_ids,
            media_group_id=aggregated.media_group_id,
            kind=CreativeKind.media,
        )
        draft.posts.append(post)
        draft.active_post_id = post.local_id
        await state.update_data({ASKED_PROJECT_TZ_KEY: False})
        await save_draft(state, draft)
        return post

    existing.media = media
    existing.source_message_ids = message_ids
    existing.kind = CreativeKind.media
    if caption and not existing.text:
        existing.text = caption
    draft.active_post_id = existing.local_id
    if not existing.channels:
        await state.update_data({ASKED_PROJECT_TZ_KEY: False})
    await save_draft(state, draft)
    return None


async def replace_post_from_album_in_project_create(
        *,
        state: FSMContext,
        user: User,
        aggregated,
        message: Message,
        bot: Bot,
        inline: InlineKeyboard,
) -> bool:
    """When user sends album to replace channel post, update that post instead of appending."""
    current_state = await state.get_state()
    if current_state != ProjectCreateState.awaiting_replace_post.state:
        return False

    data = await state.get_data()
    idx = int(data.get(MENU_CHANNEL_INDEX_KEY) or 0)
    draft = await load_draft(state)
    if draft is None or idx < 1:
        await state.set_state(ProjectCreateState.preview)
        return True

    item = get_channel_by_global_index(draft, idx)
    if item is None:
        await state.set_state(ProjectCreateState.preview)
        await _show_preview(
            bot=bot,
            state=state,
            chat_id=message.chat.id,
            draft=draft,
            user=user,
            inline=inline,
            resend_ui=True,
            answer_to=message,
        )
        return True

    post_id, _, _ = item
    post = next((p for p in draft.posts if p.local_id == post_id), None)
    if post is None:
        await state.set_state(ProjectCreateState.preview)
        return True

    old_bot_ids = list(post.bot_message_ids)
    replace_post_content_from_album(post, aggregated)
    await _sync_bot_mirror(
        bot, draft, post, chat_id=message.chat.id, old_bot_ids=old_bot_ids,
    )
    await save_draft(state, draft)
    await _show_channel_detail(
        bot=bot,
        state=state,
        chat_id=message.chat.id,
        draft=draft,
        user=user,
        inline=inline,
        channel_index=idx,
        resend_ui=True,
        answer_to=message,
    )
    return True


async def finalize_album_ingest_in_project_create(
        *,
        message: Message,
        state: FSMContext,
        user: User,
        bot: Bot,
        config: CommonConfig,
        inline: InlineKeyboard,
        resolve_channels: ResolveChannelQueries | None = None,
        newly_created_post=None,
) -> None:
    """Refresh preview / awaiting_post after album ingest without pending metadata."""
    draft = await load_draft(state)
    if draft is None:
        await state.set_state(ProjectCreateState.awaiting_post)
        return
    active = next((p for p in draft.posts if p.local_id == draft.active_post_id), None)
    if active is not None and active.source_message_ids and not active.bot_message_ids:
        await _sync_bot_mirror(bot, draft, active, chat_id=message.chat.id)
        await save_draft(state, draft)
        draft = await load_draft(state) or draft
    if newly_created_post is not None and resolve_channels is not None:
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
                message=message,
                user=user,
                bot=bot,
            )
            if bound:
                draft = await load_draft(state) or draft
                await _continue_after_batch(
                    message=message,
                    state=state,
                    user=user,
                    draft=draft,
                    config=config,
                    inline=inline,
                    bot=bot,
                )
                return
    await _maybe_show_preview_or_ask_tz(
        message=message,
        state=state,
        user=user,
        draft=draft,
        config=config,
        inline=inline,
        bot=bot,
    )
