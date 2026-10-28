from __future__ import annotations

from uuid import uuid4

from aiogram.fsm.context import FSMContext

from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import (
    CreativeKind,
)
from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    BotMediaPart,
    BotPostDraft,
    BotProjectDraft,
)
from advertiser_blogger.application.interactors_bot.project_create.parser import (
    parse_project_reply,
)
from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import (
    ResolveChannelQueries,
    collect_used_channels_from_draft,
    collect_used_swaps_from_draft,
    filter_duplicate_channel_refs,
    partition_duplicate_channel_queries,
)
from advertiser_blogger.presentation.bot.common.project_create_draft import (
    attach_channels_one_to_one,
    attach_channels_to_post,
    ensure_posts_channels_one_to_one,
    pop_pending_metadata,
    save_draft,
    sync_common_flag,
)
from configuration.common import CommonConfig


def pair_orphan_posts_with_channels(
        draft: BotProjectDraft,
        channels: list[BotChannelRef],
) -> list[BotChannelRef]:
    """
    Attach channels to orphan posts 1:1.
    Leftover channels: append to last orphan (no clones); sync common after.
    If draft already has other posts with channels, leftovers go to EMPTY.
    """
    if not channels:
        return []
    orphan_posts = [p for p in draft.posts if not p.channels]
    if not orphan_posts:
        return list(channels)

    paired = min(len(orphan_posts), len(channels))
    for idx in range(paired):
        orphan_posts[idx].channels = [channels[idx]]
    extra = channels[paired:]
    if not extra:
        sync_common_flag(draft)
        return []

    seed = orphan_posts[paired - 1]
    posts_with_channels_before = [p for p in draft.posts if p.channels and p is not seed]
    # Only absorb extras onto the orphan when this will remain a single-post draft
    # or there are no other filled posts yet (extras on the sole creative path).
    if not posts_with_channels_before:
        attach_channels_to_post(draft, seed, extra)
        sync_common_flag(draft)
        return []

    sync_common_flag(draft)
    return list(extra)


def create_empty_posts_for_channels(
        draft: BotProjectDraft,
        channels: list[BotChannelRef],
) -> None:
    if not channels:
        return
    seed = BotPostDraft(
        local_id=str(uuid4()),
        text="EMPTY",
        media=[BotMediaPart(content_type="text", text="EMPTY")],
        channels=[],
        kind=CreativeKind.empty,
    )
    draft.posts.append(seed)
    attach_channels_one_to_one(draft, seed, channels)


async def fill_orphans_leave_empty(
        *,
        state: FSMContext,
        draft: BotProjectDraft,
        resolve_channels: ResolveChannelQueries,
        config: CommonConfig,
) -> bool:
    """
    Resolve orphans on «Leave empty»:
    1) Pair pending channels with orphan posts (extras append or EMPTY)
    2) Remaining orphan posts → free swap
    3) Remaining pending channels (no posts) → EMPTY posts
    """
    changed = False

    pending_texts: list[str] = []
    while True:
        pending = await pop_pending_metadata(state)
        if not pending:
            break
        pending_texts.append(pending)

    channel_queries: list[str] = []
    for text in pending_texts:
        parsed = parse_project_reply(text)
        if parsed.project_name and not (draft.project_name and draft.project_name.strip()):
            draft.project_name = parsed.project_name
            changed = True
        if parsed.comment and not (draft.comment and draft.comment.strip()):
            draft.comment = parsed.comment
            changed = True
        channel_queries.extend(parsed.channel_queries)

    accepted: list[BotChannelRef] = []
    if channel_queries:
        exclude_urls, exclude_ids = collect_used_swaps_from_draft(draft)
        existing_channel_ids, existing_channel_keys = collect_used_channels_from_draft(draft)
        unique_queries, _ = partition_duplicate_channel_queries(
            channel_queries,
            existing_channel_ids,
            existing_channel_keys,
        )
        if unique_queries:
            resolved = await resolve_channels.resolve_many(
                unique_queries,
                timezone=config.bot_project.timezone,
                default_duration_hours=config.bot_project.default_duration_hours,
                slot_minutes=config.bot_project.slot_minutes,
                exclude_swap_urls=exclude_urls,
                exclude_swap_ids=exclude_ids,
            )
            accepted, _ = filter_duplicate_channel_refs(
                resolved,
                existing_channel_ids,
                existing_channel_keys,
            )

    if accepted:
        leftover = pair_orphan_posts_with_channels(draft, accepted)
        if leftover:
            create_empty_posts_for_channels(draft, leftover)
        changed = True

    orphan_posts = [p for p in draft.posts if not p.channels]
    if orphan_posts:
        exclude_urls, exclude_ids = collect_used_swaps_from_draft(draft)
        swaps = await resolve_channels.allocate_free_swaps(
            len(orphan_posts),
            query_raw="EMPTY",
            exclude_swap_urls=exclude_urls,
            exclude_swap_ids=exclude_ids,
        )
        for post, swap_ref in zip(orphan_posts, swaps):
            post.channels = [swap_ref]
            changed = True

    if changed:
        ensure_posts_channels_one_to_one(draft)
        await save_draft(state, draft)
    return changed
