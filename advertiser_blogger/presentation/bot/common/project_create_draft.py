from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    BotMediaPart,
    BotPostDraft,
    BotProjectDraft,
)
from advertiser_blogger.domain.record.user.entities import User

DRAFT_KEY = "bot_project_draft"
MENU_CHANNEL_INDEX_KEY = "pc_channel_index"
PREVIEW_MESSAGE_ID_KEY = "pc_preview_message_id"
PREVIEW_PAGE_KEY = "pc_preview_page"
PENDING_METADATA_KEY = "pc_pending_metadata"
PENDING_BY_REPLY_TO_KEY = "pc_pending_by_reply_to"
ASKED_PROJECT_TZ_KEY = "pc_asked_project_tz"
PROCESSING_NOTICE_KEY = "pc_processing_notice"
ORPHAN_PROMPT_MESSAGE_ID_KEY = "pc_orphan_prompt_message_id"
PENDING_CHANNEL_CHOICE_KEY = "pc_pending_channel_choice"
CHANNEL_MODE_WAITING_CALLBACK_KEY = "pc_channel_mode_waiting_cb"
PAIRING_WAITING_POST_KEY = "pc_pairing_waiting_post_id"
PC_CHANNELS_PER_PAGE = 10

_user_locks: dict[int, asyncio.Lock] = {}
_user_locks_meta = asyncio.Lock()


@asynccontextmanager
async def project_create_user_lock(telegram_id: int):
    """Serialize draft mutations for one Telegram user (mass forward race)."""
    async with _user_locks_meta:
        lock = _user_locks.setdefault(telegram_id, asyncio.Lock())
    async with lock:
        yield


async def load_draft(state: FSMContext) -> BotProjectDraft | None:
    data = await state.get_data()
    raw = data.get(DRAFT_KEY)
    if not raw:
        return None
    return BotProjectDraft.from_dict(raw)


async def save_draft(state: FSMContext, draft: BotProjectDraft) -> None:
    await state.update_data({DRAFT_KEY: draft.to_dict()})


def _pending_metadata_queue(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if item and str(item).strip()]
    text = str(raw).strip()
    return [text] if text else []


async def stash_pending_metadata(state: FSMContext, text: str) -> None:
    """Append channel/metadata text to a FIFO queue (survives album/link races)."""
    if not text or not str(text).strip():
        return
    data = await state.get_data()
    queue = _pending_metadata_queue(data.get(PENDING_METADATA_KEY))
    queue.append(str(text).strip())
    await state.update_data({PENDING_METADATA_KEY: queue})


async def pop_pending_metadata(state: FSMContext) -> str | None:
    data = await state.get_data()
    queue = _pending_metadata_queue(data.get(PENDING_METADATA_KEY))
    if not queue:
        if PENDING_METADATA_KEY in data:
            await state.update_data({PENDING_METADATA_KEY: None})
        return None
    text = queue.pop(0)
    await state.update_data({PENDING_METADATA_KEY: queue or None})
    return text


_notice_locks: dict[int, asyncio.Lock] = {}
_notice_locks_meta = asyncio.Lock()


@asynccontextmanager
async def _processing_notice_lock(chat_id: int):
    async with _notice_locks_meta:
        lock = _notice_locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        yield


async def maybe_send_processing_notice(
        message: Message,
        state: FSMContext,
        *,
        text: str,
) -> None:
    """Send at most one 'processing' notice until preview/orphan clears the flag."""
    async with _processing_notice_lock(message.chat.id):
        data = await state.get_data()
        if data.get(PROCESSING_NOTICE_KEY):
            return
        await state.update_data({PROCESSING_NOTICE_KEY: True})
        try:
            await message.answer(text)
        except Exception:
            await state.update_data({PROCESSING_NOTICE_KEY: None})


async def clear_processing_notice(state: FSMContext) -> None:
    await state.update_data({PROCESSING_NOTICE_KEY: None})


async def peek_pending_metadata(state: FSMContext) -> bool:
    data = await state.get_data()
    return bool(_pending_metadata_queue(data.get(PENDING_METADATA_KEY)))


async def stash_pending_by_reply_to(state: FSMContext, reply_to_id: int, text: str) -> None:
    data = await state.get_data()
    pending = dict(data.get(PENDING_BY_REPLY_TO_KEY) or {})
    pending[str(reply_to_id)] = text
    await state.update_data({PENDING_BY_REPLY_TO_KEY: pending})


async def pop_pending_by_reply_to_ids(
        state: FSMContext,
        message_ids: list[int],
) -> list[tuple[int, str]]:
    """Pop stashed metadata whose reply_to matches any of message_ids."""
    if not message_ids:
        return []
    data = await state.get_data()
    pending = dict(data.get(PENDING_BY_REPLY_TO_KEY) or {})
    if not pending:
        return []
    found: list[tuple[int, str]] = []
    for mid in message_ids:
        key = str(mid)
        text = pending.pop(key, None)
        if text and str(text).strip():
            found.append((mid, str(text)))
    await state.update_data({PENDING_BY_REPLY_TO_KEY: pending})
    return found


async def clear_pending_metadata(state: FSMContext) -> None:
    await state.update_data({
        PENDING_METADATA_KEY: None,
        PENDING_BY_REPLY_TO_KEY: {},
        PROCESSING_NOTICE_KEY: None,
        ORPHAN_PROMPT_MESSAGE_ID_KEY: None,
        PENDING_CHANNEL_CHOICE_KEY: None,
        CHANNEL_MODE_WAITING_CALLBACK_KEY: None,
        PAIRING_WAITING_POST_KEY: None,
    })


def _channel_batch_queue(raw: object) -> list[dict]:
    """Normalize FSM value to a list of channel-batch dicts."""
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        # Legacy single-slot → one batch.
        items = [raw]
    else:
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        out.append({
            "text": text,
            "anchor_post_id": item.get("anchor_post_id") or item.get("target_post_id"),
            "awaiting_creative": bool(item.get("awaiting_creative")),
        })
    return out


async def enqueue_channel_batch(
        state: FSMContext,
        *,
        text: str,
        anchor_post_id: str,
) -> bool:
    """
    Append an orphan channel batch. Returns True if the queue was empty
    (caller should show SMS for this batch as the new head).
    """
    text = (text or "").strip()
    if not text or not anchor_post_id:
        return False
    data = await state.get_data()
    queue = _channel_batch_queue(data.get(PENDING_CHANNEL_CHOICE_KEY))
    was_empty = not queue
    queue.append({
        "text": text,
        "anchor_post_id": anchor_post_id,
        "awaiting_creative": False,
    })
    await state.update_data({PENDING_CHANNEL_CHOICE_KEY: queue})
    return was_empty


async def peek_channel_batch(state: FSMContext) -> dict | None:
    data = await state.get_data()
    queue = _channel_batch_queue(data.get(PENDING_CHANNEL_CHOICE_KEY))
    return dict(queue[0]) if queue else None


async def pop_channel_batch(state: FSMContext) -> dict | None:
    data = await state.get_data()
    queue = _channel_batch_queue(data.get(PENDING_CHANNEL_CHOICE_KEY))
    if not queue:
        await state.update_data({PENDING_CHANNEL_CHOICE_KEY: None})
        return None
    head = queue.pop(0)
    await state.update_data({PENDING_CHANNEL_CHOICE_KEY: queue or None})
    return head


async def set_batch_awaiting_creative(state: FSMContext) -> bool:
    """Mark head batch as waiting for creative. Returns False if queue empty."""
    data = await state.get_data()
    queue = _channel_batch_queue(data.get(PENDING_CHANNEL_CHOICE_KEY))
    if not queue:
        return False
    queue[0]["awaiting_creative"] = True
    await state.update_data({PENDING_CHANNEL_CHOICE_KEY: queue})
    return True


async def peek_pending_channel_choice(state: FSMContext) -> bool:
    data = await state.get_data()
    return bool(_channel_batch_queue(data.get(PENDING_CHANNEL_CHOICE_KEY)))


def can_bind_head_to_new_post(
        head: dict | None,
        new_post: BotPostDraft | None,
        *,
        newly_created: bool,
) -> bool:
    """True only for waiting_creative + this ingest's new unbound post."""
    if not newly_created:
        return False
    if new_post is None or new_post.channels:
        return False
    if head is None or not head.get("awaiting_creative"):
        return False
    return True


async def channel_mode_preview_action(state: FSMContext) -> str:
    """
    idle → fallthrough
    waiting_callback / waiting_creative → return
    queue HEAD without prompt → show
    """
    head = await peek_channel_batch(state)
    if head is None:
        return "fallthrough"
    if head.get("awaiting_creative"):
        return "return"
    data = await state.get_data()
    if data.get(CHANNEL_MODE_WAITING_CALLBACK_KEY):
        return "return"
    return "show"


async def set_channel_mode_waiting_callback(state: FSMContext, active: bool) -> None:
    await state.update_data({CHANNEL_MODE_WAITING_CALLBACK_KEY: True if active else None})


async def exit_project_create(
        state: FSMContext,
        *,
        bot: Bot | None = None,
        chat_id: int | None = None,
) -> None:
    data = await state.get_data()
    preview_id = data.get(PREVIEW_MESSAGE_ID_KEY)
    await clear_pending_metadata(state)
    await state.clear()
    if bot is not None and chat_id is not None and preview_id is not None:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=preview_id)
        except TelegramBadRequest:
            pass


def new_draft(user: User, telegram_id: int) -> BotProjectDraft:
    return BotProjectDraft(
        draft_id=str(uuid4()),
        user_id=user.id,
        telegram_id=telegram_id,
    )


def message_to_media_parts(message: Message) -> list[BotMediaPart]:
    parts: list[BotMediaPart] = []
    text = message.text or message.caption
    if message.photo:
        parts.append(
            BotMediaPart(content_type="photo", file_id=message.photo[-1].file_id, text=text),
        )
    elif message.video:
        parts.append(
            BotMediaPart(content_type="video", file_id=message.video.file_id, text=text),
        )
    elif message.document:
        parts.append(
            BotMediaPart(content_type="document", file_id=message.document.file_id, text=text),
        )
    elif text:
        parts.append(BotMediaPart(content_type="text", text=text))
    return parts


def append_post_from_message(draft: BotProjectDraft, message: Message) -> BotPostDraft:
    from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import (
        CreativeKind,
        detect_text_creative_kind,
    )

    # Idempotent: same Telegram message must not create a duplicate post.
    for existing in draft.posts:
        if message.message_id in existing.source_message_ids:
            draft.active_post_id = existing.local_id
            return existing

    text = message.text or message.caption
    has_media = bool(
        getattr(message, "video", None)
        or getattr(message, "photo", None)
        or getattr(message, "document", None)
        or getattr(message, "animation", None)
    )
    if has_media:
        kind = CreativeKind.media
    else:
        kind = detect_text_creative_kind(text) or CreativeKind.text

    post = BotPostDraft(
        local_id=str(uuid4()),
        text=text,
        media=message_to_media_parts(message),
        source_message_ids=[message.message_id],
        media_group_id=message.media_group_id,
        kind=kind,
    )
    draft.posts.append(post)
    draft.active_post_id = post.local_id
    sync_common_flag(draft)
    return post


def clone_post_shell(source: BotPostDraft) -> BotPostDraft:
    """Copy creative content into a new post shell (no channels)."""
    return BotPostDraft(
        local_id=str(uuid4()),
        text=source.text,
        media=[
            BotMediaPart(content_type=m.content_type, file_id=m.file_id, text=m.text)
            for m in source.media
        ],
        channels=[],
        source_message_ids=list(source.source_message_ids),
        media_group_id=source.media_group_id,
        kind=source.kind,
    )


def sync_common_flag(draft: BotProjectDraft) -> None:
    """Common only when draft has exactly one post; otherwise clear."""
    if len(draft.posts) == 1:
        draft.common_post_id = draft.posts[0].local_id
    else:
        draft.common_post_id = None


def get_common_post(draft: BotProjectDraft) -> BotPostDraft | None:
    if not draft.common_post_id:
        return None
    return next((p for p in draft.posts if p.local_id == draft.common_post_id), None)


def get_sole_post(draft: BotProjectDraft) -> BotPostDraft | None:
    """Return the only post when draft has exactly one; else None."""
    if len(draft.posts) != 1:
        return None
    return draft.posts[0]


def attach_channels_to_post(
        draft: BotProjectDraft,
        target: BotPostDraft,
        channels: list[BotChannelRef],
) -> None:
    """Append all channels to one post (no clones)."""
    if not channels:
        return
    target.channels.extend(channels)
    draft.active_post_id = target.local_id
    sync_common_flag(draft)


def decide_channel_attach(
        draft: BotProjectDraft,
        target: BotPostDraft,
        channels: list[BotChannelRef],
) -> str:
    """
    Decide how to bind channels to target.

    Returns:
    - noop
    - attach  (all channels on target, no clones)
    """
    if not channels:
        return "noop"
    return "attach"


def apply_channel_attach(
        draft: BotProjectDraft,
        target: BotPostDraft,
        channels: list[BotChannelRef],
        mode: str,
) -> list[str]:
    """
    Apply a decided attach mode. Returns local_ids of posts that received channels.
    """
    if not channels or mode == "noop":
        return []
    if mode in ("attach", "single", "make_common", "append_common"):
        # Legacy mode names still append-all (no clones / no conflict).
        attach_channels_to_post(draft, target, channels)
        return [target.local_id]
    return []


def attach_channels_one_to_one(
        draft: BotProjectDraft,
        target: BotPostDraft,
        channels: list[BotChannelRef],
) -> list[str]:
    """
    Attach channels 1:1 — each channel gets its own EMPTY/cloned shell post.
    Used only for EMPTY slots, not for creative multi-channel attach.
    """
    if not channels:
        return []
    remaining = list(channels)
    attached: list[str] = []
    if not target.channels:
        target.channels = [remaining.pop(0)]
        attached.append(target.local_id)
    for ch in remaining:
        clone = clone_post_shell(target)
        clone.channels = [ch]
        draft.posts.append(clone)
        attached.append(clone.local_id)
    if attached:
        draft.active_post_id = attached[-1]
    sync_common_flag(draft)
    return attached


def ensure_posts_channels_one_to_one(draft: BotProjectDraft) -> None:
    """Keep 1:N posts intact; only sync common flag."""
    sync_common_flag(draft)


def replace_post_content_from_message(post: BotPostDraft, message: Message) -> None:
    """Replace creative of a single post; keep channels."""
    from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import (
        CreativeKind,
        detect_text_creative_kind,
    )

    text = message.text or message.caption
    has_media = bool(
        getattr(message, "video", None)
        or getattr(message, "photo", None)
        or getattr(message, "document", None)
        or getattr(message, "animation", None)
    )
    post.text = text
    post.media = message_to_media_parts(message)
    post.source_message_ids = [message.message_id]
    post.bot_message_ids = []
    post.media_group_id = message.media_group_id
    if has_media:
        post.kind = CreativeKind.media
    else:
        post.kind = detect_text_creative_kind(text) or CreativeKind.text


def replace_post_content_from_album(post: BotPostDraft, aggregated) -> None:
    """Replace creative of a single post from aggregated album; keep channels."""
    from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import (
        CreativeKind,
    )

    media = [
        BotMediaPart(
            content_type=part.media_type,
            file_id=part.file_id,
            text=part.caption,
        )
        for part in aggregated.parts
    ]
    caption = next((part.caption for part in aggregated.parts if part.caption), None)
    post.text = caption
    post.media = media
    post.source_message_ids = [p.message_id for p in aggregated.parts]
    post.bot_message_ids = []
    post.media_group_id = aggregated.media_group_id
    post.kind = CreativeKind.media


def find_post_by_source_message_id(
        draft: BotProjectDraft,
        message_id: int,
) -> BotPostDraft | None:
    for post in draft.posts:
        if message_id in post.source_message_ids:
            return post
    return None


def remove_post_from_draft(draft: BotProjectDraft, post_local_id: str) -> bool:
    """Remove a post by local_id. Returns True if removed."""
    before = len(draft.posts)
    draft.posts = [p for p in draft.posts if p.local_id != post_local_id]
    if len(draft.posts) == before:
        return False
    if draft.active_post_id == post_local_id:
        draft.active_post_id = draft.posts[-1].local_id if draft.posts else None
    sync_common_flag(draft)
    return True


def resolve_target_post(
        draft: BotProjectDraft,
        reply_to_message_id: int | None = None,
) -> BotPostDraft | None:
    """reply_to binds that post even if it already has channels. Unbound lists: last post without channels."""
    if not draft.posts:
        return None
    if reply_to_message_id is not None:
        matched = [
            p for p in draft.posts
            if reply_to_message_id in p.source_message_ids
        ]
        if matched:
            return matched[-1]
        return None
    without_channels = [p for p in draft.posts if not p.channels]
    if without_channels:
        return without_channels[-1]
    return None


def last_post_with_channels(draft: BotProjectDraft) -> BotPostDraft | None:
    for post in reversed(draft.posts):
        if post.channels:
            return post
    return None


def all_posts_have_channels(draft: BotProjectDraft) -> bool:
    return bool(draft.posts) and all(bool(p.channels) for p in draft.posts)


def has_post_waiting_for_channels(draft: BotProjectDraft) -> bool:
    return any(not p.channels for p in draft.posts)


def draft_ready_for_preview(draft: BotProjectDraft) -> bool:
    return all_posts_have_channels(draft) and draft.start_at is not None and draft.end_at is not None


def flat_channels(draft: BotProjectDraft) -> list[tuple[str, int, object]]:
    """Return list of (post_local_id, index_in_post, channel_ref) with global 1-based indices separately."""
    items = []
    for post in draft.posts:
        for idx, ch in enumerate(post.channels):
            items.append((post.local_id, idx, ch))
    return items


def get_channel_by_global_index(draft: BotProjectDraft, global_index: int):
    items = flat_channels(draft)
    if global_index < 1 or global_index > len(items):
        return None
    return items[global_index - 1]
