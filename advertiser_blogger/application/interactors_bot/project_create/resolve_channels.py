from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from advertiser_blogger.application.interactors_bot.project_create.channel_query_parser import (
    ParsedChannelQueryLine,
    parse_channel_query_line,
)
from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    BotProjectDraft,
    ChannelRefStatus,
    ParsedScheduleFragments,
)
from advertiser_blogger.application.interactors_bot.project_create.schedule import (
    resolve_project_schedule,
)
from advertiser_blogger.domain.record.channel.constants import Format

SWAP_CHANNEL_POOL: tuple[str, ...] = (
    "https://t.me/channel_swap1",
    "https://t.me/channel_swap2",
    "https://t.me/channel_swap3",
    "https://t.me/channel_swap4",
    "https://t.me/channel_swap5",
    "https://t.me/channel_swap6",
    "https://t.me/channel_swap7",
    "https://t.me/channel_swap8",
    "https://t.me/channel_swap9",
    "https://t.me/channel_swap10",
    "https://t.me/channel_swap11",
    "https://t.me/channel_swap12",
    "https://t.me/channel_swap13",
    "https://t.me/channel_swap14",
    "https://t.me/channel_swap15",
    "https://t.me/channel_swap16",
    "https://t.me/channel_swap17",
    "https://t.me/channel_swap18",
    "https://t.me/channel_swap19",
    "https://t.me/channel_swap20",
)
# Backward-compatible alias (first pool slot).
SWAP_CHANNEL_URL = SWAP_CHANNEL_POOL[0]
SWAP_CHANNEL_FALLBACK = "https://t.me/blogix_swap_channel"


def swap_url_key(url: str | None) -> str:
    if not url:
        return ""
    return url.strip().lower().rstrip("/")


def collect_used_swaps_from_channels(
        channels: list[BotChannelRef],
) -> tuple[set[str], set[UUID]]:
    """Return (url_keys, channel_ids) already assigned as swap."""
    urls: set[str] = set()
    ids: set[UUID] = set()
    for ch in channels:
        if not ch.is_swap:
            continue
        key = swap_url_key(ch.url)
        if key:
            urls.add(key)
        if ch.channel_id is not None:
            ids.add(ch.channel_id)
    return urls, ids


def collect_used_swaps_from_draft(
        draft: BotProjectDraft,
        *,
        skip_post_id: str | None = None,
        skip_post_channel: tuple[str, int] | None = None,
) -> tuple[set[str], set[UUID]]:
    """Swaps already used in draft, optionally skipping a post or one channel slot."""
    channels: list[BotChannelRef] = []
    for post in draft.posts:
        if skip_post_id is not None and post.local_id == skip_post_id:
            continue
        for idx, ch in enumerate(post.channels):
            if skip_post_channel is not None and (post.local_id, idx) == skip_post_channel:
                continue
            channels.append(ch)
    return collect_used_swaps_from_channels(channels)


def channel_query_key(query: str) -> str:
    text = (query or "").strip()
    if not text:
        return ""
    candidates = normalize_channel_url_candidates(text)
    if candidates:
        return candidates[0].lower().rstrip("/")
    return text.lower()


def channel_ref_alert_label(ref: BotChannelRef) -> str:
    name = (ref.display_name or "").strip()
    url = (ref.url or "").strip()
    if name and url:
        return f"{name} ({url})"
    return name or url or ref.query_raw


def collect_used_channels_from_draft(
        draft: BotProjectDraft,
        *,
        skip_post_id: str | None = None,
        skip_post_channel: tuple[str, int] | None = None,
) -> tuple[set[UUID], set[str]]:
    """Return (channel_ids, normalized query keys) already present in draft."""
    ids: set[UUID] = set()
    keys: set[str] = set()
    for post in draft.posts:
        if skip_post_id is not None and post.local_id == skip_post_id:
            continue
        for idx, ch in enumerate(post.channels):
            if skip_post_channel is not None and (post.local_id, idx) == skip_post_channel:
                continue
            if ch.channel_id is not None:
                ids.add(ch.channel_id)
            key = channel_query_key(ch.query_raw)
            if key:
                keys.add(key)
    return ids, keys


def partition_duplicate_channel_queries(
        queries: list[str],
        existing_ids: set[UUID],
        existing_keys: set[str],
) -> tuple[list[str], list[str]]:
    """Drop duplicate queries; return (unique_queries, labels for alerts)."""
    seen_keys = set(existing_keys)
    unique: list[str] = []
    duplicate_labels: list[str] = []
    for query in queries:
        parsed = parse_channel_query_line(query)
        raw = (parsed.channel_query or query).strip()
        key = channel_query_key(raw)
        if not key or key in seen_keys:
            duplicate_labels.append(raw or query.strip())
            continue
        seen_keys.add(key)
        unique.append(query)
    return unique, duplicate_labels


def filter_duplicate_channel_refs(
        refs: list[BotChannelRef],
        existing_ids: set[UUID],
        existing_keys: set[str],
) -> tuple[list[BotChannelRef], list[str]]:
    seen_keys = set(existing_keys)
    seen_ids = set(existing_ids)
    accepted: list[BotChannelRef] = []
    duplicate_labels: list[str] = []
    for ref in refs:
        key = channel_query_key(ref.query_raw)
        cid = ref.channel_id
        if (cid is not None and cid in seen_ids) or (key and key in seen_keys):
            duplicate_labels.append(channel_ref_alert_label(ref))
            continue
        accepted.append(ref)
        if cid is not None:
            seen_ids.add(cid)
        if key:
            seen_keys.add(key)
    return accepted, duplicate_labels


_USERNAME_RE = re.compile(
    r"(?:https?://)?(?:t|telegram)\.me/\+([A-Za-z0-9_-]{8,})"
    r"|(?:https?://)?(?:t|telegram)\.me/joinchat/([A-Za-z0-9_-]{8,})"
    r"|(?:https?://)?(?:t|telegram)\.me/([A-Za-z0-9_]{4,})"
    r"|@([A-Za-z0-9_]{4,})",
    re.IGNORECASE,
)


def normalize_channel_url_candidates(query: str) -> list[str]:
    text = query.strip()
    match = _USERNAME_RE.search(text)
    if match:
        plus_hash = match.group(1)
        joinchat_hash = match.group(2)
        username = (match.group(3) or match.group(4) or "").lstrip("@")
        if plus_hash:
            invite = f"+{plus_hash}"
            return [
                f"https://t.me/{invite}",
                f"http://t.me/{invite}",
                f"https://telegram.me/{invite}",
                f"http://telegram.me/{invite}",
            ]
        if joinchat_hash:
            path = f"joinchat/{joinchat_hash}"
            return [
                f"https://t.me/{path}",
                f"http://t.me/{path}",
                f"https://telegram.me/{path}",
                f"http://telegram.me/{path}",
            ]
        if username:
            return [
                f"https://t.me/{username}",
                f"http://t.me/{username}",
                f"https://telegram.me/{username}",
                f"http://telegram.me/{username}",
            ]
    lowered = text.lower()
    if lowered.startswith("http"):
        return [lowered]
    if text.startswith("@"):
        username = text[1:]
        return [
            f"https://t.me/{username}",
            f"http://t.me/{username}",
        ]
    return [f"https://t.me/{text.lstrip('@')}", text]


_PUBLIC_USERNAME_URL_RE = re.compile(
    r"^(?:https?://)?(?:t|telegram)\.me/([A-Za-z0-9_]{4,})/?$",
    re.IGNORECASE,
)


def extract_public_username(query_or_url: str) -> str | None:
    """Public @username from query/URL; None for invites / joinchat."""
    text = (query_or_url or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if "+/" in lowered or "joinchat/" in lowered or "/+" in lowered:
        return None
    for candidate in normalize_channel_url_candidates(text):
        if "joinchat/" in candidate.lower() or "/+" in candidate:
            continue
        match = _PUBLIC_USERNAME_URL_RE.match(candidate.strip())
        if match:
            return match.group(1)
    return None


def expand_trailing_s_url_candidates(
        base_candidates: list[str],
        *,
        max_s: int = 20,
) -> list[str]:
    """URLs where username is base + 's'*k (k=1..max_s). Invites skipped."""
    out: list[str] = []
    seen: set[str] = set()
    for base in base_candidates:
        username = extract_public_username(base)
        if not username:
            continue
        for k in range(1, max_s + 1):
            suffixed = f"{username}{'s' * k}"
            for url in (
                f"https://t.me/{suffixed}",
                f"http://t.me/{suffixed}",
                f"https://telegram.me/{suffixed}",
                f"http://telegram.me/{suffixed}",
            ):
                key = url.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(url)
    return out


def trailing_s_suffix_len(url: str | None, base_username: str | None) -> int | None:
    """How many trailing s after base_username in URL username; None if not a match."""
    if not url or not base_username:
        return None
    found = extract_public_username(url)
    if not found:
        return None
    base = base_username
    if len(found) <= len(base) or not found.startswith(base):
        return None
    suffix = found[len(base) :]
    if not suffix or set(suffix) != {"s"}:
        return None
    return len(suffix)


def build_swap_channel_comment(
        queries: list[str],
        user_comment: str | None = None,
        *,
        channel_notes: list[str] | None = None,
) -> str:
    cleaned = [q.strip() for q in queries if q and q.strip()]
    if not cleaned:
        return ""
    n = len(cleaned)
    lines = [f"Надо заменить {n} каналов:"]
    notes = channel_notes or []
    for i, query in enumerate(cleaned, start=1):
        note = notes[i - 1] if i - 1 < len(notes) else ""
        if note:
            lines.append(f"{i}. {query} ({note})")
        else:
            lines.append(f"{i}. {query}")
    if user_comment and user_comment.strip():
        lines.append("")
        lines.append(f"Комментарий: {user_comment.strip()}")
    return "\n".join(lines)


def build_swap_order_comment(
        ref: BotChannelRef,
        user_comment: str | None = None,
) -> str:
    """Comment for a single 1:1 swap order (query + optional notes / overflow)."""
    lines = [f"Заменить: {ref.query_raw}"]
    if ref.comment and ref.comment.strip():
        lines.append(ref.comment.strip())
    elif user_comment and user_comment.strip():
        lines.append(f"Комментарий: {user_comment.strip()}")
    if ref.start_at and ref.end_at:
        lines.append(
            f"{ref.start_at.strftime('%d.%m.%Y')} "
            f"{ref.start_at.strftime('%H:%M')}–{ref.end_at.strftime('%H:%M')}"
        )
    return "\n".join(lines)


def build_swap_channel_comment_from_refs(
        refs: list[BotChannelRef],
        user_comment: str | None = None,
) -> str:
    queries: list[str] = []
    notes: list[str] = []
    for ch in refs:
        if not ch.is_swap:
            continue
        queries.append(ch.query_raw)
        parts: list[str] = []
        if ch.comment:
            parts.append(ch.comment)
        if ch.start_at and ch.end_at:
            parts.append(
                f"{ch.start_at.strftime('%d.%m.%Y')} "
                f"{ch.start_at.strftime('%H:%M')}–{ch.end_at.strftime('%H:%M')}"
            )
        notes.append("; ".join(parts))
    return build_swap_channel_comment(queries, user_comment=user_comment, channel_notes=notes)


def _append_overflow_comment(ref: BotChannelRef, overflow_queries: list[str]) -> None:
    if not overflow_queries:
        return
    block = build_swap_channel_comment(overflow_queries)
    if not block:
        return
    if ref.comment and ref.comment.strip():
        ref.comment = f"{ref.comment.strip()}\n\n{block}"
    else:
        ref.comment = block


def _schedule_fragments_present(schedule: ParsedScheduleFragments) -> bool:
    return bool(schedule.date or schedule.start_time or schedule.end_time or schedule.relative_day)


def resolve_bot_form_schedule(
        fragments: ParsedScheduleFragments | None,
        *,
        timezone: str = "Asia/Tashkent",
        default_duration_hours: int = 2,
        slot_minutes: int = 5,
        now: datetime | None = None,
):
    """Bot RK form: resolve fragments; past date/time → nearest available slot."""
    schedule = resolve_project_schedule(
        fragments,
        now=now,
        timezone=timezone,
        default_duration_hours=default_duration_hours,
        slot_minutes=slot_minutes,
        allow_past=True,
    )
    current = now if now is not None else datetime.now(tz=schedule.start_at.tzinfo)
    if current.tzinfo is None:
        current = current.replace(tzinfo=schedule.start_at.tzinfo)
    else:
        current = current.astimezone(schedule.start_at.tzinfo)

    if schedule.start_at < current:
        return resolve_project_schedule(
            None,
            now=now,
            timezone=timezone,
            default_duration_hours=default_duration_hours,
            slot_minutes=slot_minutes,
        )
    return schedule


def apply_channel_line_meta(
        ref: BotChannelRef,
        parsed: ParsedChannelQueryLine,
        *,
        timezone: str = "Asia/Tashkent",
        default_duration_hours: int = 2,
        slot_minutes: int = 5,
) -> BotChannelRef:
    """Attach comment/schedule from a parsed channel line onto the resolved ref."""
    ref.query_raw = parsed.channel_query.strip() or ref.query_raw
    if parsed.comment:
        ref.comment = parsed.comment
    if _schedule_fragments_present(parsed.schedule):
        schedule = resolve_bot_form_schedule(
            parsed.schedule,
            timezone=timezone,
            default_duration_hours=default_duration_hours,
            slot_minutes=slot_minutes,
        )
        ref.start_at = schedule.start_at
        ref.end_at = schedule.end_at
        ref.schedule_source = schedule.source
    return ref


class ChannelResolver:
    """Resolve channel queries to channel_id (found | unknown | swap)."""

    def __init__(self, find_channels_by_urls, get_channel_by_id):
        self._find_channels_by_urls = find_channels_by_urls
        self._get_channel_by_id = get_channel_by_id

    async def resolve(self, query: str, *, swap_url: str | None = None) -> BotChannelRef:
        candidates = normalize_channel_url_candidates(query)
        found = await self._find_channels_by_urls(urls=candidates)
        if found:
            return await self._ref_from_found(
                query=query, channel_id=found[0].channel_id, fallback_url=candidates[0], is_swap=False,
            )

        soft = expand_trailing_s_url_candidates(candidates)
        if soft:
            soft_found = await self._find_channels_by_urls(urls=soft)
            if soft_found:
                base_user = extract_public_username(query) or extract_public_username(candidates[0])
                best_id = soft_found[0].channel_id
                best_url = soft[0]
                best_len: int | None = None
                for item in soft_found:
                    channel = await self._get_channel_by_id(channel_id=item.channel_id)
                    url = channel.channel.url if channel is not None else ""
                    score = trailing_s_suffix_len(url, base_user)
                    if score is None:
                        continue
                    if best_len is None or score < best_len:
                        best_len = score
                        best_id = item.channel_id
                        best_url = url or best_url
                return await self._ref_from_found(
                    query=query,
                    channel_id=best_id,
                    fallback_url=best_url,
                    is_swap=False,
                )

        if not swap_url:
            return BotChannelRef(status=ChannelRefStatus.unknown, query_raw=query)

        swap_candidates = normalize_channel_url_candidates(swap_url)
        swap_found = await self._find_channels_by_urls(urls=swap_candidates)
        if not swap_found:
            return BotChannelRef(status=ChannelRefStatus.unknown, query_raw=query)
        return await self._ref_from_found(
            query=query,
            channel_id=swap_found[0].channel_id,
            fallback_url=swap_candidates[0],
            is_swap=True,
        )

    async def _ref_from_found(
            self,
            *,
            query: str,
            channel_id: UUID,
            fallback_url: str,
            is_swap: bool,
    ) -> BotChannelRef:
        channel = await self._get_channel_by_id(channel_id=channel_id)
        display_name = None
        url = fallback_url
        fmt: Format | None = None
        if channel is not None:
            display_name = channel.channel.name
            url = channel.channel.url
            if channel.format:
                def _price_value(price) -> float:
                    return float(price.price) if hasattr(price, "price") else float(price)

                cheapest = min(channel.format, key=lambda f: _price_value(f.price))
                fmt = cheapest.name
        if fmt is None:
            return BotChannelRef(
                status=ChannelRefStatus.invalid,
                query_raw=query,
                channel_id=channel_id,
                display_name=display_name,
                url=url,
                format=None,
                is_swap=is_swap,
            )
        return BotChannelRef(
            status=ChannelRefStatus.found,
            query_raw=query,
            channel_id=channel_id,
            display_name=display_name,
            url=url,
            format=fmt,
            is_swap=is_swap,
        )


class ChannelFormatsResolver:
    """Validate that a found channel already has a format (set by ChannelResolver)."""

    async def resolve(self, ref: BotChannelRef) -> BotChannelRef:
        if ref.status != ChannelRefStatus.found:
            return ref
        if ref.format is not None:
            return ref
        return BotChannelRef(
            status=ChannelRefStatus.invalid,
            query_raw=ref.query_raw,
            channel_id=ref.channel_id,
            display_name=ref.display_name,
            url=ref.url,
            format=None,
            is_swap=ref.is_swap,
            comment=ref.comment,
            start_at=ref.start_at,
            end_at=ref.end_at,
            schedule_source=ref.schedule_source,
        )


class ResolveChannelQueries:
    def __init__(
            self,
            channel_resolver: ChannelResolver,
            formats_resolver: ChannelFormatsResolver,
            *,
            swap_pool: tuple[str, ...] = SWAP_CHANNEL_POOL,
            swap_fallback: str | None = SWAP_CHANNEL_FALLBACK,
    ):
        self._channel_resolver = channel_resolver
        self._formats_resolver = formats_resolver
        self._swap_pool = swap_pool
        self._swap_fallback = swap_fallback

    def _swap_candidates(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for url in self._swap_pool:
            key = url.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(url)
        if self._swap_fallback:
            key = self._swap_fallback.strip().lower()
            if key and key not in seen:
                out.append(self._swap_fallback)
        return out

    async def resolve_many(
            self,
            queries: list[str],
            *,
            timezone: str = "Asia/Tashkent",
            default_duration_hours: int = 2,
            slot_minutes: int = 5,
            exclude_swap_urls: set[str] | None = None,
            exclude_swap_ids: set[UUID] | None = None,
    ) -> list[BotChannelRef]:
        result: list[BotChannelRef] = []
        seen: set[str] = set()
        swap_cursor = 0
        swap_candidates = self._swap_candidates()
        used_urls = {swap_url_key(u) for u in (exclude_swap_urls or set()) if swap_url_key(u)}
        used_ids = set(exclude_swap_ids or set())
        last_swap_ref: BotChannelRef | None = None
        overflow_queries: list[str] = []

        for query in queries:
            parsed = parse_channel_query_line(query)
            channel_key = (parsed.channel_query or query).strip().lower()
            if not channel_key or channel_key in seen:
                continue
            seen.add(channel_key)

            # Probe: resolve without swap first to detect missing channels.
            probe = await self._channel_resolver.resolve(
                query=parsed.channel_query or query,
                swap_url=None,
            )
            if probe.status == ChannelRefStatus.found and not probe.is_swap:
                ref = await self._formats_resolver.resolve(ref=probe)
                ref = apply_channel_line_meta(
                    ref,
                    parsed,
                    timezone=timezone,
                    default_duration_hours=default_duration_hours,
                    slot_minutes=slot_minutes,
                )
                result.append(ref)
                continue

            assigned: BotChannelRef | None = None
            while swap_cursor < len(swap_candidates):
                swap_url = swap_candidates[swap_cursor]
                swap_cursor += 1
                if swap_url_key(swap_url) in used_urls:
                    continue
                ref = await self._channel_resolver.resolve(
                    query=parsed.channel_query or query,
                    swap_url=swap_url,
                )
                if not (ref.status == ChannelRefStatus.found and ref.is_swap):
                    continue
                if ref.channel_id is not None and ref.channel_id in used_ids:
                    continue
                ref = await self._formats_resolver.resolve(ref=ref)
                if ref.status != ChannelRefStatus.found or ref.format is None:
                    # Slot exists but has no format — try next candidate.
                    continue
                ref = apply_channel_line_meta(
                    ref,
                    parsed,
                    timezone=timezone,
                    default_duration_hours=default_duration_hours,
                    slot_minutes=slot_minutes,
                )
                used_urls.add(swap_url_key(ref.url or swap_url))
                if ref.channel_id is not None:
                    used_ids.add(ref.channel_id)
                assigned = ref
                last_swap_ref = ref
                break

            if assigned is not None:
                result.append(assigned)
            elif last_swap_ref is not None:
                # Pool/fallback exhausted but we already have at least one swap —
                # fold into last swap comment (overflow).
                overflow_queries.append(parsed.channel_query or query)
            else:
                result.append(
                    BotChannelRef(
                        status=ChannelRefStatus.unknown,
                        query_raw=parsed.channel_query or query,
                    )
                )

        if overflow_queries and last_swap_ref is not None:
            _append_overflow_comment(last_swap_ref, overflow_queries)

        return result

    async def allocate_free_swaps(
            self,
            count: int,
            *,
            query_raw: str = "EMPTY",
            exclude_swap_urls: set[str] | None = None,
            exclude_swap_ids: set[UUID] | None = None,
    ) -> list[BotChannelRef]:
        """Assign up to `count` free swap slots (1:1), skipping already used ones."""
        if count <= 0:
            return []
        result: list[BotChannelRef] = []
        swap_cursor = 0
        swap_candidates = self._swap_candidates()
        used_urls = {swap_url_key(u) for u in (exclude_swap_urls or set()) if swap_url_key(u)}
        used_ids = set(exclude_swap_ids or set())

        for index in range(count):
            assigned: BotChannelRef | None = None
            while swap_cursor < len(swap_candidates):
                swap_url = swap_candidates[swap_cursor]
                swap_cursor += 1
                if swap_url_key(swap_url) in used_urls:
                    continue
                ref = await self._channel_resolver.resolve(
                    query=query_raw if count == 1 else f"{query_raw}#{index + 1}",
                    swap_url=swap_url,
                )
                if not (ref.status == ChannelRefStatus.found and ref.is_swap):
                    continue
                if ref.channel_id is not None and ref.channel_id in used_ids:
                    continue
                ref = await self._formats_resolver.resolve(ref=ref)
                if ref.status != ChannelRefStatus.found or ref.format is None:
                    continue
                used_urls.add(swap_url_key(ref.url or swap_url))
                if ref.channel_id is not None:
                    used_ids.add(ref.channel_id)
                assigned = ref
                break
            if assigned is None:
                break
            result.append(assigned)
        return result
