import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    ChannelRefStatus,
)
from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import (
    SWAP_CHANNEL_FALLBACK,
    SWAP_CHANNEL_POOL,
    SWAP_CHANNEL_URL,
    ChannelFormatsResolver,
    ChannelResolver,
    ResolveChannelQueries,
    build_swap_channel_comment,
    build_swap_channel_comment_from_refs,
    build_swap_order_comment,
    normalize_channel_url_candidates,
)
from advertiser_blogger.domain.record.channel.constants import Format


def _default_formats():
    return [
        SimpleNamespace(name=Format.telegram_24, price=200.0),
        SimpleNamespace(name=Format.telegram_1_24, price=50.0),
    ]


def _channel_full(name: str, url: str, *, formats=None):
    return SimpleNamespace(
        channel=SimpleNamespace(name=name, url=url),
        format=list(formats) if formats is not None else _default_formats(),
    )


def test_normalize_username_and_url():
    assert "https://t.me/foo_bar" in normalize_channel_url_candidates("@foo_bar")
    assert "https://t.me/foo_bar" in normalize_channel_url_candidates("https://t.me/foo_bar")
    assert "https://telegram.me/foo_bar" in normalize_channel_url_candidates("t.me/foo_bar")
    assert "https://t.me/+EdifkdTPC8s2Y2Fi" in normalize_channel_url_candidates(
        "https://t.me/+EdifkdTPC8s2Y2Fi"
    )


def test_resolve_invite_link_unknown_goes_to_swap():
    swap_id = uuid4()

    async def find_channels_by_urls(urls):
        if any("channel_swap1" in u for u in urls):
            return [SimpleNamespace(channel_id=swap_id)]
        return []

    async def get_channel_by_id(*, channel_id):
        return _channel_full("Swap 1", "https://t.me/channel_swap1")

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
        swap_fallback=None,
    )
    refs = asyncio.run(resolver.resolve_many(["https://t.me/+EdifkdTPC8s2Y2Fi"]))
    assert len(refs) == 1
    assert refs[0].status == ChannelRefStatus.found
    assert refs[0].is_swap is True
    assert refs[0].query_raw == "https://t.me/+EdifkdTPC8s2Y2Fi"
    assert refs[0].channel_id == swap_id
    assert refs[0].format == Format.telegram_1_24


def test_swap_pool_has_20_slots():
    assert len(SWAP_CHANNEL_POOL) == 20
    assert SWAP_CHANNEL_POOL[0] == "https://t.me/channel_swap1"
    assert SWAP_CHANNEL_POOL[-1] == "https://t.me/channel_swap20"
    assert SWAP_CHANNEL_URL == SWAP_CHANNEL_POOL[0]


def test_build_swap_channel_comment():
    assert build_swap_channel_comment(["@foo", " https://t.me/bar "]) == (
        "Надо заменить 2 каналов:\n"
        "1. @foo\n"
        "2. https://t.me/bar"
    )
    assert build_swap_channel_comment(["@only"]) == (
        "Надо заменить 1 каналов:\n"
        "1. @only"
    )
    assert build_swap_channel_comment(["@foo"], user_comment="  hello  ") == (
        "Надо заменить 1 каналов:\n"
        "1. @foo\n"
        "\n"
        "Комментарий: hello"
    )
    assert build_swap_channel_comment(["@foo"], user_comment="   ") == (
        "Надо заменить 1 каналов:\n"
        "1. @foo"
    )


def test_resolve_unknown_maps_to_first_swap_slot():
    swap_id = uuid4()

    async def find_channels_by_urls(urls):
        if any("channel_swap1" in u for u in urls):
            return [SimpleNamespace(channel_id=swap_id)]
        return []

    async def get_channel_by_id(*, channel_id):
        return _channel_full("Swap 1", "https://t.me/channel_swap1")

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
    )

    refs = asyncio.run(resolver.resolve_many(["@missing_channel"]))
    assert len(refs) == 1
    assert refs[0].status == ChannelRefStatus.found
    assert refs[0].is_swap is True
    assert refs[0].query_raw == "@missing_channel"
    assert refs[0].channel_id == swap_id
    assert refs[0].display_name == "Swap 1"
    assert refs[0].format == Format.telegram_1_24


def test_resolve_unknown_stays_unknown_when_swap_missing():
    async def find_channels_by_urls(urls):
        return []

    resolver = ChannelResolver(
        find_channels_by_urls=find_channels_by_urls,
        get_channel_by_id=AsyncMock(),
    )
    ref = asyncio.run(resolver.resolve("@missing_channel"))
    assert ref.status == ChannelRefStatus.unknown
    assert ref.is_swap is False
    assert ref.query_raw == "@missing_channel"


def test_resolve_found_channel_is_not_swap():
    channel_id = uuid4()

    async def find_channels_by_urls(urls):
        if any("real_channel" in u for u in urls):
            return [SimpleNamespace(channel_id=channel_id)]
        return []

    async def get_channel_by_id(*, channel_id):
        return _channel_full("Real", "https://t.me/real_channel")

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
    )
    refs = asyncio.run(resolver.resolve_many(["@real_channel"]))
    assert refs[0].is_swap is False
    assert refs[0].channel_id == channel_id


def test_resolve_many_assigns_swap_one_to_one():
    id1, id2 = uuid4(), uuid4()

    async def find_channels_by_urls(urls):
        if any("channel_swap1" in u for u in urls):
            return [SimpleNamespace(channel_id=id1)]
        if any("channel_swap2" in u for u in urls):
            return [SimpleNamespace(channel_id=id2)]
        return []

    async def get_channel_by_id(*, channel_id):
        url = "https://t.me/channel_swap1" if channel_id == id1 else "https://t.me/channel_swap2"
        return _channel_full(url, url)

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
    )
    refs = asyncio.run(resolver.resolve_many(["@miss_a", "@miss_b"]))
    assert len(refs) == 2
    assert refs[0].channel_id == id1
    assert refs[1].channel_id == id2
    assert refs[0].query_raw == "@miss_a"
    assert refs[1].query_raw == "@miss_b"


def test_resolve_many_overflow_goes_to_last_swap_comment():
    pool = ("https://t.me/channel_swap1", "https://t.me/channel_swap2")
    id1, id2 = uuid4(), uuid4()

    async def find_channels_by_urls(urls):
        if any("channel_swap1" in u for u in urls):
            return [SimpleNamespace(channel_id=id1)]
        if any("channel_swap2" in u for u in urls):
            return [SimpleNamespace(channel_id=id2)]
        return []

    async def get_channel_by_id(*, channel_id):
        return _channel_full("Swap", "https://t.me/channel_swap1")

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
        swap_pool=pool,
        swap_fallback=None,
    )
    refs = asyncio.run(
        resolver.resolve_many(["@a", "@b", "@c", "@d"])
    )
    assert len(refs) == 2
    assert refs[0].query_raw == "@a"
    assert refs[1].query_raw == "@b"
    assert "Надо заменить 2 каналов:" in (refs[1].comment or "")
    assert "@c" in (refs[1].comment or "")
    assert "@d" in (refs[1].comment or "")


def test_resolve_many_skips_missing_pool_slot():
    id2 = uuid4()

    async def find_channels_by_urls(urls):
        if any("channel_swap2" in u for u in urls):
            return [SimpleNamespace(channel_id=id2)]
        return []

    async def get_channel_by_id(*, channel_id):
        return _channel_full("Swap 2", "https://t.me/channel_swap2")

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
        swap_pool=(
            "https://t.me/channel_swap1",
            "https://t.me/channel_swap2",
        ),
        swap_fallback=None,
    )
    refs = asyncio.run(resolver.resolve_many(["@missing"]))
    assert len(refs) == 1
    assert refs[0].status == ChannelRefStatus.found
    assert refs[0].is_swap is True
    assert refs[0].channel_id == id2
    assert refs[0].query_raw == "@missing"


def test_resolve_many_falls_back_to_blogix_when_pool_empty():
    blogix_id = uuid4()

    async def find_channels_by_urls(urls):
        if any("blogix_swap_channel" in u for u in urls):
            return [SimpleNamespace(channel_id=blogix_id)]
        return []

    async def get_channel_by_id(*, channel_id):
        return _channel_full("Blogix | Канал на замену", SWAP_CHANNEL_FALLBACK)

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
        swap_pool=("https://t.me/channel_swap1", "https://t.me/channel_swap2"),
    )
    refs = asyncio.run(resolver.resolve_many(["@missing"]))
    assert len(refs) == 1
    assert refs[0].status == ChannelRefStatus.found
    assert refs[0].is_swap is True
    assert refs[0].channel_id == blogix_id
    assert refs[0].display_name == "Blogix | Канал на замену"


def test_resolve_many_found_channel_does_not_consume_pool():
    real_id, swap_id = uuid4(), uuid4()

    async def find_channels_by_urls(urls):
        if any("real_channel" in u for u in urls):
            return [SimpleNamespace(channel_id=real_id)]
        if any("channel_swap1" in u for u in urls):
            return [SimpleNamespace(channel_id=swap_id)]
        return []

    async def get_channel_by_id(*, channel_id):
        if channel_id == real_id:
            return _channel_full("Real", "https://t.me/real_channel")
        return _channel_full("Swap 1", "https://t.me/channel_swap1")

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
        swap_pool=("https://t.me/channel_swap1",),
        swap_fallback=None,
    )
    refs = asyncio.run(resolver.resolve_many(["@real_channel", "@missing"]))
    assert len(refs) == 2
    assert refs[0].is_swap is False
    assert refs[0].channel_id == real_id
    assert refs[1].is_swap is True
    assert refs[1].channel_id == swap_id


def test_resolve_many_skips_already_used_swap_from_other_post():
    id1, id2 = uuid4(), uuid4()

    async def find_channels_by_urls(urls):
        if any("channel_swap1" in u for u in urls):
            return [SimpleNamespace(channel_id=id1)]
        if any("channel_swap2" in u for u in urls):
            return [SimpleNamespace(channel_id=id2)]
        return []

    async def get_channel_by_id(*, channel_id):
        url = (
            "https://t.me/channel_swap1"
            if channel_id == id1
            else "https://t.me/channel_swap2"
        )
        return _channel_full(url, url)

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
        swap_pool=(
            "https://t.me/channel_swap1",
            "https://t.me/channel_swap2",
        ),
        swap_fallback=None,
    )
    refs = asyncio.run(
        resolver.resolve_many(
            ["@missing_on_post_b"],
            exclude_swap_urls={"https://t.me/channel_swap1"},
            exclude_swap_ids={id1},
        )
    )
    assert len(refs) == 1
    assert refs[0].is_swap is True
    assert refs[0].channel_id == id2
    assert refs[0].url == "https://t.me/channel_swap2"


def test_collect_used_swaps_from_draft_skips_post():
    from advertiser_blogger.application.interactors_bot.project_create.models import (
        BotPostDraft,
        BotProjectDraft,
    )
    from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import (
        collect_used_swaps_from_draft,
    )

    id1, id2 = uuid4(), uuid4()
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[
            BotPostDraft(
                local_id="p1",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@a",
                        channel_id=id1,
                        url="https://t.me/channel_swap1",
                        is_swap=True,
                    )
                ],
            ),
            BotPostDraft(
                local_id="p2",
                channels=[
                    BotChannelRef(
                        status=ChannelRefStatus.found,
                        query_raw="@b",
                        channel_id=id2,
                        url="https://t.me/channel_swap2",
                        is_swap=True,
                    )
                ],
            ),
        ],
    )
    urls, ids = collect_used_swaps_from_draft(draft, skip_post_id="p2")
    assert urls == {"https://t.me/channel_swap1"}
    assert ids == {id1}


def test_resolve_many_parses_comment_on_swap_line():
    swap_id = uuid4()

    async def find_channels_by_urls(urls):
        if any("channel_swap1" in u for u in urls):
            return [SimpleNamespace(channel_id=swap_id)]
        return []

    async def get_channel_by_id(*, channel_id):
        return _channel_full("Swap 1", "https://t.me/channel_swap1")

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
    )
    refs = asyncio.run(
        resolver.resolve_many(
            ["https://t.me/ru2ch комментарий - любое время завтра"],
            timezone="Asia/Tashkent",
        )
    )
    assert len(refs) == 1
    assert refs[0].is_swap is True
    assert refs[0].query_raw == "https://t.me/ru2ch"
    assert refs[0].comment == "любое время"
    assert refs[0].start_at is not None
    assert refs[0].end_at is not None

    text = build_swap_order_comment(refs[0])
    assert "https://t.me/ru2ch" in text
    assert "любое время" in text

    text_multi = build_swap_channel_comment_from_refs(refs)
    assert "https://t.me/ru2ch" in text_multi


def test_allocate_free_swaps_skips_used_and_returns_count():
    swap_ids = {f"https://t.me/channel_swap{i}": uuid4() for i in range(1, 4)}

    async def find_channels_by_urls(urls):
        for url, channel_id in swap_ids.items():
            if any(url in u for u in urls):
                return [SimpleNamespace(channel_id=channel_id)]
        return []

    async def get_channel_by_id(*, channel_id):
        for url, sid in swap_ids.items():
            if sid == channel_id:
                return _channel_full(url.rsplit("/", 1)[-1], url)
        return None

    resolver = ResolveChannelQueries(
        channel_resolver=ChannelResolver(
            find_channels_by_urls=find_channels_by_urls,
            get_channel_by_id=get_channel_by_id,
        ),
        formats_resolver=ChannelFormatsResolver(),
        swap_fallback=None,
    )
    used_url = "https://t.me/channel_swap1"
    refs = asyncio.run(
        resolver.allocate_free_swaps(
            2,
            query_raw="EMPTY",
            exclude_swap_urls={used_url},
        )
    )
    assert len(refs) == 2
    assert all(r.is_swap and r.status == ChannelRefStatus.found for r in refs)
    assert refs[0].url == "https://t.me/channel_swap2"
    assert refs[1].url == "https://t.me/channel_swap3"
    assert refs[0].query_raw == "EMPTY#1"
    assert refs[1].query_raw == "EMPTY#2"


def test_channel_resolver_picks_cheapest_format() -> None:
    channel_id = uuid4()

    async def find_channels_by_urls(urls):
        return [SimpleNamespace(channel_id=channel_id)]

    async def get_channel_by_id(*, channel_id):
        return _channel_full(
            "Foo",
            "https://t.me/foo",
            formats=[
                SimpleNamespace(name=Format.telegram_24, price=200.0),
                SimpleNamespace(name=Format.telegram_1_24, price=50.0),
                SimpleNamespace(name=Format.telegram_2_48, price=120.0),
            ],
        )

    resolver = ChannelResolver(
        find_channels_by_urls=find_channels_by_urls,
        get_channel_by_id=get_channel_by_id,
    )
    out = asyncio.run(resolver.resolve("@foo"))
    assert out.status == ChannelRefStatus.found
    assert out.format == Format.telegram_1_24


def test_soft_match_trailing_s_url():
    soft_id = uuid4()

    async def find_channels_by_urls(urls):
        if any(u.rstrip("/").lower().endswith("ru2chsss") for u in urls):
            return [SimpleNamespace(channel_id=soft_id)]
        return []

    async def get_channel_by_id(*, channel_id):
        return _channel_full("News", "https://t.me/ru2chsss")

    resolver = ChannelResolver(
        find_channels_by_urls=find_channels_by_urls,
        get_channel_by_id=get_channel_by_id,
    )
    out = asyncio.run(resolver.resolve("https://t.me/ru2ch"))
    assert out.status == ChannelRefStatus.found
    assert out.channel_id == soft_id
    assert out.url == "https://t.me/ru2chsss"
    assert out.is_swap is False


def test_soft_match_prefers_shortest_trailing_s():
    short_id = uuid4()
    long_id = uuid4()

    async def find_channels_by_urls(urls):
        hits = []
        for u in urls:
            key = u.rstrip("/").lower()
            if key.endswith("ru2chs") and not key.endswith("ru2chss"):
                hits.append(SimpleNamespace(channel_id=short_id))
            elif key.endswith("ru2chsss"):
                hits.append(SimpleNamespace(channel_id=long_id))
        # unique by id
        seen = set()
        out = []
        for h in hits:
            if h.channel_id not in seen:
                seen.add(h.channel_id)
                out.append(h)
        return out

    async def get_channel_by_id(*, channel_id):
        if channel_id == short_id:
            return _channel_full("S", "https://t.me/ru2chs")
        return _channel_full("SSS", "https://t.me/ru2chsss")

    resolver = ChannelResolver(
        find_channels_by_urls=find_channels_by_urls,
        get_channel_by_id=get_channel_by_id,
    )
    out = asyncio.run(resolver.resolve("https://t.me/ru2ch"))
    assert out.channel_id == short_id
    assert out.url == "https://t.me/ru2chs"


def test_exact_match_beats_trailing_s():
    exact_id = uuid4()
    soft_id = uuid4()

    async def find_channels_by_urls(urls):
        for u in urls:
            key = u.rstrip("/").lower()
            if key.endswith("/ru2ch") or key.endswith(".me/ru2ch"):
                return [SimpleNamespace(channel_id=exact_id)]
            if "ru2chsss" in key:
                return [SimpleNamespace(channel_id=soft_id)]
        return []

    async def get_channel_by_id(*, channel_id):
        if channel_id == exact_id:
            return _channel_full("Exact", "https://t.me/ru2ch")
        return _channel_full("Soft", "https://t.me/ru2chsss")

    resolver = ChannelResolver(
        find_channels_by_urls=find_channels_by_urls,
        get_channel_by_id=get_channel_by_id,
    )
    out = asyncio.run(resolver.resolve("https://t.me/ru2ch"))
    assert out.channel_id == exact_id
