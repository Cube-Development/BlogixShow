from __future__ import annotations

from structlog import get_logger
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka import FromDishka

from advertiser_blogger.application.common.bot.collect_start_payload import CollectStartPayload
from advertiser_blogger.application.common.exceptions.application_error import (
    AccessDenied,
    ManagerNotFound,
    OrderNotFound,
    OrderToMatchNotFound,
    ProjectNotFound,
)
from advertiser_blogger.application.interactors_bot.collect_createorder_post.dto import (
    CollectCreateorderAcceptInput,
)
from advertiser_blogger.application.interactors_bot.collect_createorder_post.use_case import (
    CollectCreateorderAcceptPost,
)
from advertiser_blogger.application.interactors_bot.project_create.models import BotPostDraft
from advertiser_blogger.domain.record.user.entities import User
from advertiser_blogger.presentation.bot.common.collect_createorder_draft import (
    clear_collect_post_draft,
    load_collect_order_id,
    load_collect_post_draft,
    load_collect_project_id,
    load_collect_session_id,
    save_collect_post_draft,
    clear_collect_fsm_if_session_matches,
    collect_session_matches,
    start_new_collect_session,
)
from advertiser_blogger.presentation.bot.common.collect_createorder_fsm import (
    chat_accept_lock,
    collect_chat_mutations_lock,
)
from advertiser_blogger.presentation.bot.common.collect_createorder_urls import (
    build_collect_createorder_return_url,
    edit_collect_callback_text,
    edit_collect_success_notification,
)
from advertiser_blogger.presentation.bot.common.mirror_post_messages import mirror_post_messages
from advertiser_blogger.presentation.bot.common.project_create_draft import (
    message_to_media_parts,
    replace_post_content_from_album,
)
from advertiser_blogger.presentation.bot.filters.collect_createorder_message import (
    IsNotTelegramBotCommand,
)
from advertiser_blogger.presentation.bot.filters.collect_createorder_stale import (
    IsCollectCreateorderStaleCallback,
)
from advertiser_blogger.presentation.bot.filters.get_user import GetUserByTelegramId
from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard
from advertiser_blogger.presentation.bot.states.collect_createorder import CollectCreateorderState
from configuration.common import CommonConfig

logger = get_logger(__name__)

CollectCreateorderRouter = Router(name="CollectCreateorderRouter")

PROMPT_SEND_POST = "🌠 Отправьте сюда готовый пост"
PROMPT_CHECK_POST = "Проверьте пост и нажмите «Принять» или «Заменить пост»."
SUCCESS_ACCEPT = "Пост принят, можно продолжить."
CANCEL_COLLECT_TEXT = "Сбор поста отменён."
ACCEPT_IN_PROGRESS_TEXT = "Пост ещё сохраняется, подождите."
STALE_SESSION_TEXT = "Сессия устарела. Отправьте /start ещё раз."
UNLINKED_TELEGRAM_TEXT = (
    "Свяжите Telegram с аккаунтом Blogix на сайте, затем откройте ссылку снова."
)
_COLLECT_CALLBACKS = frozenset({"cco_accept", "cco_replace", "cco_cancel"})


async def _safe_callback_answer(callback: CallbackQuery, text: str | None = None) -> None:
    try:
        await callback.answer(text=text)
    except Exception:
        logger.warning("collect: callback answer failed", exc_info=True)


async def begin_collect_createorder_from_start(
        message: Message,
        state: FSMContext,
        user: User,
        payload: CollectStartPayload,
        bot: Bot,
        db_gateway,
) -> None:
    from advertiser_blogger.application.interactors_bot.collect_createorder_post.auth import (
        assert_collect_createorder_access,
    )

    try:
        await assert_collect_createorder_access(
            db_gateway,
            user_id=user.id,
            project_id=payload.project_id,
            order_id=payload.order_id,
        )
    except (ProjectNotFound, AccessDenied, ManagerNotFound, OrderNotFound):
        await bot.send_message(chat_id=message.chat.id, text="Нет доступа к проекту ⛔️")
        return

    await state.clear()
    await start_new_collect_session(
        state,
        project_id=payload.project_id,
        order_id=payload.order_id,
    )
    await state.set_state(CollectCreateorderState.awaiting_post)
    try:
        await bot.send_message(
            chat_id=message.chat.id,
            text=PROMPT_SEND_POST,
            reply_markup=InlineKeyboard().collect_createorder_cancel(),
        )
    except TelegramBadRequest:
        logger.warning("collect: begin prompt send failed", chat_id=message.chat.id, exc_info=True)


async def handle_collect_start_decode_error(message: Message, bot: Bot) -> None:
    await bot.send_message(
        chat_id=message.chat.id,
        text="Некорректная ссылка. Откройте проект на сайте и получите новую.",
    )


@CollectCreateorderRouter.message(
    StateFilter(CollectCreateorderState.awaiting_post, CollectCreateorderState.awaiting_accept),
    ~GetUserByTelegramId(),
    IsNotTelegramBotCommand(),
)
async def collect_unlinked_message(message: Message, bot: Bot) -> None:
    await bot.send_message(chat_id=message.chat.id, text=UNLINKED_TELEGRAM_TEXT)


@CollectCreateorderRouter.message(
    StateFilter(CollectCreateorderState.awaiting_post, CollectCreateorderState.awaiting_accept),
    GetUserByTelegramId(),
    IsNotTelegramBotCommand(),
)
async def collect_receive_post_message(
        message: Message,
        state: FSMContext,
        bot: Bot,
        inline: FromDishka[InlineKeyboard],
) -> None:
    if message.media_group_id is not None:
        return
    async with collect_chat_mutations_lock(message.chat.id):
        post = _build_post_from_message(message)
        await _show_preview_and_accept(message=message, state=state, bot=bot, inline=inline, post=post)


@CollectCreateorderRouter.callback_query(
    StateFilter(CollectCreateorderState.awaiting_accept),
    F.data == "cco_replace",
    GetUserByTelegramId(),
)
async def collect_replace_post(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
        inline: FromDishka[InlineKeyboard],
) -> None:
    chat_id = callback.message.chat.id if callback.message else callback.from_user.id
    async with collect_chat_mutations_lock(chat_id):
        if await state.get_state() != CollectCreateorderState.awaiting_accept.state:
            await _safe_callback_answer(callback)
            return
        await _safe_callback_answer(callback)
        await clear_collect_post_draft(state)
        await state.set_state(CollectCreateorderState.awaiting_post)
        try:
            await edit_collect_callback_text(
                bot=bot,
                callback=callback,
                text=PROMPT_SEND_POST,
                reply_markup=inline.collect_createorder_cancel(),
            )
        except TelegramBadRequest:
            logger.warning("collect: replace prompt edit failed", exc_info=True)


@CollectCreateorderRouter.callback_query(
    StateFilter(CollectCreateorderState.awaiting_accept),
    F.data == "cco_accept",
    GetUserByTelegramId(),
)
async def collect_accept_post(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
        user: User,
        accept_post: FromDishka[CollectCreateorderAcceptPost],
        config: FromDishka[CommonConfig],
        inline: FromDishka[InlineKeyboard],
) -> None:
    chat_id = callback.message.chat.id if callback.message else callback.from_user.id
    lock = chat_accept_lock(chat_id)
    if lock.locked():
        await _safe_callback_answer(callback, ACCEPT_IN_PROGRESS_TEXT)
        return

    async with lock:
        accept_session_id = await load_collect_session_id(state)
        project_id = await load_collect_project_id(state)
        order_id = await load_collect_order_id(state)
        post = await load_collect_post_draft(state)
        if project_id is None or post is None or not post.source_message_ids:
            await _safe_callback_answer(callback)
            try:
                await edit_collect_callback_text(
                    bot=bot,
                    callback=callback,
                    text="Пост не найден. Отправьте креатив снова.",
                    reply_markup=inline.collect_createorder_cancel(),
                )
            except TelegramBadRequest:
                logger.warning("collect: missing draft edit failed", exc_info=True)
            if await collect_session_matches(state, accept_session_id):
                await state.set_state(CollectCreateorderState.awaiting_post)
            return

        await _safe_callback_answer(callback)
        persisted = False
        try:
            await accept_post(
                data=CollectCreateorderAcceptInput(
                    user_id=user.id,
                    telegram_chat_id=callback.from_user.id,
                    project_id=project_id,
                    order_id=order_id,
                    post=post,
                ),
            )
            persisted = True
        except (ProjectNotFound, AccessDenied, ManagerNotFound, OrderNotFound) as exc:
            logger.warning("collect: accept denied", reason=str(exc))
            try:
                await edit_collect_callback_text(
                    bot=bot,
                    callback=callback,
                    text="Нет доступа к проекту ⛔️",
                )
            except TelegramBadRequest:
                logger.warning("collect: accept denied edit failed", exc_info=True)
        except OrderToMatchNotFound:
            try:
                await edit_collect_callback_text(
                    bot=bot,
                    callback=callback,
                    text="Нет подходящих заказов для универсального поста в этом проекте.",
                )
            except TelegramBadRequest:
                logger.warning("collect: accept no orders edit failed", exc_info=True)
        except Exception:
            logger.exception("collect: accept failed", project_id=project_id)
            try:
                await edit_collect_callback_text(
                    bot=bot,
                    callback=callback,
                    text="Не удалось сохранить пост. Попробуйте снова.",
                    reply_markup=inline.collect_createorder_accept(),
                )
            except TelegramBadRequest:
                logger.warning("collect: accept retry edit failed", exc_info=True)

        if not persisted:
            return

        project_url = build_collect_createorder_return_url(
            frontend_domain=config.bot.frontend_domain,
            project_id=project_id,
        )
        try:
            await edit_collect_success_notification(
                bot=bot,
                callback=callback,
                success_text=SUCCESS_ACCEPT,
                project_url=project_url,
                inline_success_keyboard=inline.collect_createorder_success(project_url=project_url),
            )
        except TelegramBadRequest:
            logger.warning("collect: success message edit failed", project_id=project_id, exc_info=True)
        finally:
            try:
                await clear_collect_fsm_if_session_matches(state, accept_session_id)
            except Exception:
                logger.exception("collect: state clear failed", chat_id=chat_id)


@CollectCreateorderRouter.callback_query(
    StateFilter(CollectCreateorderState.awaiting_post, CollectCreateorderState.awaiting_accept),
    F.data == "cco_cancel",
    GetUserByTelegramId(),
)
async def collect_cancel(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
) -> None:
    chat_id = callback.message.chat.id if callback.message else callback.from_user.id
    async with collect_chat_mutations_lock(chat_id):
        current = await state.get_state()
        if current not in {
            CollectCreateorderState.awaiting_post.state,
            CollectCreateorderState.awaiting_accept.state,
        }:
            await _safe_callback_answer(callback)
            return
        await _safe_callback_answer(callback)
        await state.clear()
        try:
            await edit_collect_callback_text(
                bot=bot,
                callback=callback,
                text=CANCEL_COLLECT_TEXT,
            )
        except TelegramBadRequest:
            logger.warning("collect: cancel edit failed", exc_info=True)


@CollectCreateorderRouter.callback_query(
    F.data.in_(_COLLECT_CALLBACKS),
    ~GetUserByTelegramId(),
)
async def collect_unlinked_callback(callback: CallbackQuery, bot: Bot) -> None:
    await _safe_callback_answer(callback)
    try:
        await edit_collect_callback_text(
            bot=bot,
            callback=callback,
            text=UNLINKED_TELEGRAM_TEXT,
        )
    except TelegramBadRequest:
        logger.warning("collect: unlinked callback edit failed", exc_info=True)


@CollectCreateorderRouter.callback_query(IsCollectCreateorderStaleCallback())
async def collect_stale_callback(callback: CallbackQuery, bot: Bot) -> None:
    await _safe_callback_answer(callback, STALE_SESSION_TEXT)
    try:
        await edit_collect_callback_text(
            bot=bot,
            callback=callback,
            text=STALE_SESSION_TEXT,
        )
    except TelegramBadRequest:
        logger.warning("collect: stale session message edit failed", exc_info=True)


def _build_post_from_message(message: Message) -> BotPostDraft:
    from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import (
        CreativeKind,
        detect_text_creative_kind,
    )

    text = message.text or message.caption
    has_media = bool(message.photo or message.video or message.document or message.animation)
    if has_media:
        kind = CreativeKind.media
    else:
        kind = detect_text_creative_kind(text) or CreativeKind.text
    return BotPostDraft(
        local_id=str(uuid4()),
        text=text,
        media=message_to_media_parts(message),
        source_message_ids=[message.message_id],
        media_group_id=message.media_group_id,
        kind=kind,
    )


async def _show_preview_and_accept(
        *,
        message: Message,
        state: FSMContext,
        bot: Bot,
        inline: InlineKeyboard,
        post: BotPostDraft,
) -> None:
    await save_collect_post_draft(state, post)
    await state.set_state(CollectCreateorderState.awaiting_accept)
    copied_ids = await mirror_post_messages(
        bot,
        chat_id=message.chat.id,
        source_message_ids=post.source_message_ids,
    )
    if not copied_ids:
        try:
            await bot.send_message(chat_id=message.chat.id, text="Пост получен.")
        except TelegramBadRequest:
            logger.warning("collect: preview copy fallback failed", exc_info=True)
    try:
        await bot.send_message(
            chat_id=message.chat.id,
            text=PROMPT_CHECK_POST,
            reply_markup=inline.collect_createorder_accept(),
        )
    except TelegramBadRequest:
        logger.warning("collect: preview accept keyboard send failed", exc_info=True)
        try:
            await bot.send_message(chat_id=message.chat.id, text=PROMPT_CHECK_POST)
        except TelegramBadRequest:
            logger.warning("collect: preview prompt send failed", exc_info=True)


async def collect_receive_album(
        *,
        state: FSMContext,
        message: Message,
        bot: Bot,
        inline: InlineKeyboard,
        aggregated,
) -> bool:
    current = await state.get_state()
    if not current or not str(current).startswith("CollectCreateorderState"):
        return False
    if str(current) not in {
        CollectCreateorderState.awaiting_post.state,
        CollectCreateorderState.awaiting_accept.state,
    }:
        return False
    post = await load_collect_post_draft(state)
    if post is None or str(current) == CollectCreateorderState.awaiting_post.state:
        from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import CreativeKind

        from advertiser_blogger.application.interactors_bot.project_create.models import BotMediaPart

        media = [
            BotMediaPart(
                content_type=part.media_type,
                file_id=part.file_id,
                text=part.caption,
            )
            for part in aggregated.parts
        ]
        caption = next((p.caption for p in aggregated.parts if p.caption), None)
        post = BotPostDraft(
            local_id=str(uuid4()),
            text=caption,
            media=media,
            source_message_ids=[p.message_id for p in aggregated.parts],
            media_group_id=aggregated.media_group_id,
            kind=CreativeKind.media,
        )
    else:
        replace_post_content_from_album(post, aggregated)
    async with collect_chat_mutations_lock(message.chat.id):
        await _show_preview_and_accept(message=message, state=state, bot=bot, inline=inline, post=post)
    return True
