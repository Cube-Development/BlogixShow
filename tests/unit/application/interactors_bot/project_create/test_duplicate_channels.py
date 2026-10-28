from uuid import uuid4

from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    BotPostDraft,
    BotProjectDraft,
    ChannelRefStatus,
)
from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import (
    channel_query_key,
    collect_used_channels_from_draft,
    filter_duplicate_channel_refs,
    partition_duplicate_channel_queries,
)
from advertiser_blogger.domain.record.channel.constants import Format


def _ref(
        *,
        query: str,
        channel_id=None,
        name: str | None = None,
        url: str | None = None,
) -> BotChannelRef:
    return BotChannelRef(
        status=ChannelRefStatus.found,
        query_raw=query,
        channel_id=channel_id or uuid4(),
        display_name=name,
        url=url,
        format=Format.telegram_1_24,
    )


def test_channel_query_key_normalizes_username_and_url() -> None:
    assert channel_query_key("@Foo_Bar") == channel_query_key("https://t.me/Foo_Bar")


def test_partition_duplicate_channel_queries_in_batch_and_draft() -> None:
    cid = uuid4()
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[
            BotPostDraft(
                local_id="p1",
                channels=[_ref(query="@existing", channel_id=cid)],
            )
        ],
    )
    existing_ids, existing_keys = collect_used_channels_from_draft(draft)
    unique, dups = partition_duplicate_channel_queries(
        ["@existing", "@new_channel", "@new_channel"],
        existing_ids,
        existing_keys,
    )
    assert unique == ["@new_channel"]
    assert dups == ["@existing", "@new_channel"]


def test_filter_duplicate_channel_refs_by_channel_id() -> None:
    cid = uuid4()
    existing_ids = {cid}
    existing_keys = {"https://t.me/existing"}
    refs = [
        _ref(
            query="@existing",
            channel_id=cid,
            name="Existing",
            url="https://t.me/existing",
        ),
        _ref(
            query="@other",
            name="Other",
            url="https://t.me/other",
        ),
    ]
    accepted, dups = filter_duplicate_channel_refs(refs, existing_ids, existing_keys)
    assert len(accepted) == 1
    assert accepted[0].query_raw == "@other"
    assert dups == ["Existing (https://t.me/existing)"]


def test_collect_used_channels_skips_target_post() -> None:
    id1, id2 = uuid4(), uuid4()
    draft = BotProjectDraft(
        draft_id="d1",
        user_id=uuid4(),
        telegram_id=1,
        posts=[
            BotPostDraft(
                local_id="p1",
                channels=[_ref(query="@a", channel_id=id1)],
            ),
            BotPostDraft(
                local_id="p2",
                channels=[_ref(query="@b", channel_id=id2)],
            ),
        ],
    )
    ids, keys = collect_used_channels_from_draft(draft, skip_post_id="p2")
    assert ids == {id1}
    assert "https://t.me/a" in keys
    assert "https://t.me/b" not in keys
