from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from aiogram.fsm.context import FSMContext

from advertiser_blogger.application.interactors_bot.project_create.models import BotPostDraft

COLLECT_PROJECT_ID_KEY = "cco_project_id"
COLLECT_ORDER_ID_KEY = "cco_order_id"
COLLECT_POST_KEY = "cco_post_draft"
COLLECT_SESSION_ID_KEY = "cco_session_id"


async def save_collect_context(
        state: FSMContext,
        *,
        project_id: UUID,
        order_id: UUID | None,
) -> None:
    await state.update_data({
        COLLECT_PROJECT_ID_KEY: str(project_id),
        COLLECT_ORDER_ID_KEY: str(order_id) if order_id else None,
    })


async def load_collect_project_id(state: FSMContext) -> UUID | None:
    data = await state.get_data()
    raw = data.get(COLLECT_PROJECT_ID_KEY)
    if not raw:
        return None
    return UUID(str(raw))


async def load_collect_order_id(state: FSMContext) -> UUID | None:
    data = await state.get_data()
    raw = data.get(COLLECT_ORDER_ID_KEY)
    if not raw:
        return None
    return UUID(str(raw))


async def load_collect_session_id(state: FSMContext) -> str | None:
    data = await state.get_data()
    raw = data.get(COLLECT_SESSION_ID_KEY)
    return str(raw) if raw else None


async def start_new_collect_session(
        state: FSMContext,
        *,
        project_id: UUID,
        order_id: UUID | None,
) -> str:
    session_id = str(uuid4())
    await state.update_data({COLLECT_SESSION_ID_KEY: session_id})
    await save_collect_context(state, project_id=project_id, order_id=order_id)
    return session_id


async def collect_session_matches(state: FSMContext, session_id: str | None) -> bool:
    current = await load_collect_session_id(state)
    if session_id is None:
        return current is None
    return current == session_id


async def clear_collect_fsm_if_session_matches(state: FSMContext, session_id: str | None) -> bool:
    if not await collect_session_matches(state, session_id):
        return False
    await state.clear()
    return True


async def clear_collect_post_draft(state: FSMContext) -> None:
    await state.update_data({COLLECT_POST_KEY: None})


async def save_collect_post_draft(state: FSMContext, post: BotPostDraft) -> None:
    await state.update_data({COLLECT_POST_KEY: _post_to_dict(post)})


async def load_collect_post_draft(state: FSMContext) -> BotPostDraft | None:
    data = await state.get_data()
    raw = data.get(COLLECT_POST_KEY)
    if not raw:
        return None
    return _post_from_dict(raw)


def _post_to_dict(post: BotPostDraft) -> dict[str, Any]:
    return {
        "local_id": post.local_id,
        "text": post.text,
        "source_message_ids": list(post.source_message_ids),
        "bot_message_ids": list(post.bot_message_ids),
        "media_group_id": post.media_group_id,
        "kind": post.kind.value if hasattr(post.kind, "value") else str(post.kind),
        "media": [
            {
                "content_type": m.content_type,
                "file_id": m.file_id,
                "text": m.text,
            }
            for m in post.media
        ],
    }


def _post_from_dict(data: dict[str, Any]) -> BotPostDraft:
    from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import CreativeKind
    from advertiser_blogger.application.interactors_bot.project_create.models import BotMediaPart

    media = [
        BotMediaPart(
            content_type=m["content_type"],
            file_id=m.get("file_id"),
            text=m.get("text"),
        )
        for m in data.get("media") or []
    ]
    kind_raw = data.get("kind") or CreativeKind.media.value
    try:
        kind = CreativeKind(kind_raw)
    except ValueError:
        kind = CreativeKind.media
    return BotPostDraft(
        local_id=data["local_id"],
        text=data.get("text"),
        media=media,
        source_message_ids=list(data.get("source_message_ids") or []),
        bot_message_ids=list(data.get("bot_message_ids") or []),
        media_group_id=data.get("media_group_id"),
        kind=kind,
    )
