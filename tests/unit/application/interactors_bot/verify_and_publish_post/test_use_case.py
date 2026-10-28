import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from advertiser_blogger.application.interactors_bot.match_and_attach_post.use_case import (
    MatchAndAttachPostInteractor,
)
from advertiser_blogger.application.interactors_bot.publish_post_broadcast.dto import (
    PublishPostBroadcastDtoOutput, PublishPostResult,
)
from advertiser_blogger.application.interactors_bot.verify_and_publish_post.dto import (
    LowSimilarity, NoOrders, Success, VerifyAndPublishPostDtoInput,
)
from advertiser_blogger.application.interactors_bot.verify_and_publish_post.use_case import (
    VerifyAndPublishPostInteractor,
)
from advertiser_blogger.domain.common.text_similarity import POST_SIMILARITY_TOKEN_SET_THRESHOLD
from advertiser_blogger.domain.read.order.entities.order_candidate import OrderCandidate
from advertiser_blogger.presentation.bot.common.extract_post_submission import PostSubmissionInput

USER_ID = uuid.uuid4()
ORDER_ID = uuid.uuid4()
POST_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()
CHANNEL_IDENT = 3992737086
CHANNEL_IDENT_DB = -1001234567890

TZ_TEXT = (
    "blogix рекламная биржа в узбекистане где вы работаете по системе "
    "а не вручную подбор и бронирование размещений"
)
OTHER_TEXT = "совершенно другой пост про корзинку и акции супермаркета"


def _make_interactor(
        candidates: list[OrderCandidate],
        fetch_map: dict[str, str | None],
        project_candidates: list[OrderCandidate] | None = None,
) -> tuple[VerifyAndPublishPostInteractor, AsyncMock]:
    db_gateway = MagicMock()
    db_gateway.resolve_channel_ident_in_db = AsyncMock(return_value=CHANNEL_IDENT_DB)
    db_gateway.get_channel_ident_by_username = AsyncMock(return_value=None)
    db_gateway.read_today_order_candidates_by_channel = AsyncMock(return_value=candidates)
    db_gateway.read_today_order_candidates_by_project = AsyncMock(
        return_value=project_candidates if project_candidates is not None else candidates,
    )
    db_gateway.read_order_candidate_by_order_id = AsyncMock(
        return_value=candidates[0] if candidates else None,
    )
    db_gateway.close = AsyncMock()

    record_gateway = MagicMock()
    record_gateway.is_exist_post = AsyncMock(return_value=None)
    record_gateway.close = AsyncMock()

    async def fetch_text(post_url: str) -> str | None:
        return fetch_map.get(post_url)

    post_text_provider = MagicMock()
    post_text_provider.fetch_text = AsyncMock(side_effect=fetch_text)

    publish_interactor = AsyncMock(
        return_value=PublishPostBroadcastDtoOutput(
            results=[
                PublishPostResult(
                    order_id=ORDER_ID,
                    post_url="https://t.me/blogger/6",
                    success=True,
                ),
            ],
        ),
    )
    match_interactor = MatchAndAttachPostInteractor(
        read_gateway=db_gateway,
        record_gateway=record_gateway,
        publish_interactor=publish_interactor,
        post_text_provider=post_text_provider,
    )
    return (
        VerifyAndPublishPostInteractor(
            db_gateway=db_gateway,
            match_interactor=match_interactor,
            post_text_provider=post_text_provider,
        ),
        post_text_provider,
    )


def test_tz_url_fetched_and_matches_blogger_post() -> None:
    interactor, provider = _make_interactor(
        candidates=[OrderCandidate(order_id=ORDER_ID, post_id=POST_ID, texts=["https://t.me/source/4"])],
        fetch_map={
            "https://t.me/source/4": TZ_TEXT,
            "https://t.me/blogger/6": TZ_TEXT,
        },
    )
    result = asyncio.run(
        interactor(
            VerifyAndPublishPostDtoInput(
                user_id=USER_ID,
                telegram_id=1,
                submission=PostSubmissionInput(
                    channel_ident=CHANNEL_IDENT,
                    channel_username="blogger",
                    post_url="https://t.me/blogger/6",
                    text=None,
                ),
            ),
        ),
    )
    assert isinstance(result, Success)
    assert result.score >= POST_SIMILARITY_TOKEN_SET_THRESHOLD
    interactor.db_gateway.resolve_channel_ident_in_db.assert_awaited_once_with(channel_ident=CHANNEL_IDENT)
    interactor.match_interactor.read_gateway.read_today_order_candidates_by_channel.assert_awaited_once()
    call_kwargs = interactor.match_interactor.read_gateway.read_today_order_candidates_by_channel.await_args.kwargs
    assert call_kwargs["channel_ident"] == CHANNEL_IDENT_DB
    provider.fetch_text.assert_any_await(post_url="https://t.me/source/4")
    provider.fetch_text.assert_any_await(post_url="https://t.me/blogger/6")


def test_tz_url_with_different_blogger_post_returns_low_similarity() -> None:
    interactor, _ = _make_interactor(
        candidates=[OrderCandidate(order_id=ORDER_ID, post_id=POST_ID, texts=["https://t.me/source/4"])],
        fetch_map={
            "https://t.me/source/4": TZ_TEXT,
            "https://t.me/blogger/6": OTHER_TEXT,
        },
    )
    result = asyncio.run(
        interactor(
            VerifyAndPublishPostDtoInput(
                user_id=USER_ID,
                telegram_id=1,
                submission=PostSubmissionInput(
                    channel_ident=CHANNEL_IDENT,
                    channel_username="blogger",
                    post_url="https://t.me/blogger/6",
                    text=None,
                ),
            ),
        ),
    )
    assert isinstance(result, LowSimilarity)
    assert result.best_score < POST_SIMILARITY_TOKEN_SET_THRESHOLD


def test_forward_url_only_fetches_by_post_url() -> None:
    interactor, provider = _make_interactor(
        candidates=[OrderCandidate(order_id=ORDER_ID, post_id=POST_ID, texts=[TZ_TEXT])],
        fetch_map={"https://t.me/blogger/6": TZ_TEXT},
    )
    result = asyncio.run(
        interactor(
            VerifyAndPublishPostDtoInput(
                user_id=USER_ID,
                telegram_id=1,
                submission=PostSubmissionInput(
                    channel_ident=CHANNEL_IDENT,
                    channel_username="blogger",
                    post_url="https://t.me/blogger/6",
                    text="https://t.me/blogger/6",
                ),
            ),
        ),
    )
    assert isinstance(result, Success)
    assert result.score >= POST_SIMILARITY_TOKEN_SET_THRESHOLD
    provider.fetch_text.assert_any_await(post_url="https://t.me/blogger/6")


def test_channel_ident_not_in_db_returns_no_orders() -> None:
    interactor, _ = _make_interactor(
        candidates=[],
        fetch_map={},
    )
    interactor.db_gateway.resolve_channel_ident_in_db = AsyncMock(return_value=None)
    result = asyncio.run(
        interactor(
            VerifyAndPublishPostDtoInput(
                user_id=USER_ID,
                telegram_id=1,
                submission=PostSubmissionInput(
                    channel_ident=CHANNEL_IDENT,
                    channel_username="testblogix_4",
                    post_url="https://t.me/testblogix_4/10",
                    text="post text",
                ),
            ),
        ),
    )
    assert isinstance(result, NoOrders)
    interactor.db_gateway.resolve_channel_ident_in_db.assert_awaited_once_with(channel_ident=CHANNEL_IDENT)
    interactor.db_gateway.get_channel_ident_by_username.assert_not_awaited()
    interactor.match_interactor.read_gateway.read_today_order_candidates_by_channel.assert_not_awaited()


def test_public_post_url_resolves_channel_by_username() -> None:
    interactor, provider = _make_interactor(
        candidates=[OrderCandidate(order_id=ORDER_ID, post_id=POST_ID, texts=[TZ_TEXT])],
        fetch_map={"https://t.me/testblogix_4/11": TZ_TEXT},
    )
    interactor.db_gateway.get_channel_ident_by_username = AsyncMock(return_value=CHANNEL_IDENT_DB)
    result = asyncio.run(
        interactor(
            VerifyAndPublishPostDtoInput(
                user_id=USER_ID,
                telegram_id=1,
                submission=PostSubmissionInput(
                    channel_ident=None,
                    channel_username="testblogix_4",
                    post_url="https://t.me/testblogix_4/11",
                    text=None,
                ),
            ),
        ),
    )
    assert isinstance(result, Success)
    interactor.db_gateway.resolve_channel_ident_in_db.assert_not_awaited()
    interactor.db_gateway.get_channel_ident_by_username.assert_awaited_once_with(username="testblogix_4")
    call_kwargs = interactor.match_interactor.read_gateway.read_today_order_candidates_by_channel.await_args.kwargs
    assert call_kwargs["channel_ident"] == CHANNEL_IDENT_DB
    provider.fetch_text.assert_awaited_once_with(post_url="https://t.me/testblogix_4/11")


def test_project_scope_uses_project_candidates_query() -> None:
    interactor, _ = _make_interactor(
        candidates=[],
        fetch_map={"https://t.me/blogger/6": TZ_TEXT},
        project_candidates=[OrderCandidate(order_id=ORDER_ID, post_id=POST_ID, texts=[TZ_TEXT])],
    )
    result = asyncio.run(
        interactor(
            VerifyAndPublishPostDtoInput(
                user_id=USER_ID,
                telegram_id=1,
                submission=PostSubmissionInput(
                    channel_ident=CHANNEL_IDENT,
                    channel_username="blogger",
                    post_url="https://t.me/blogger/6",
                    text=None,
                ),
                project_id=PROJECT_ID,
            ),
        ),
    )
    assert isinstance(result, Success)
    interactor.match_interactor.read_gateway.read_today_order_candidates_by_project.assert_awaited_once()
    interactor.match_interactor.read_gateway.read_today_order_candidates_by_channel.assert_not_awaited()


def test_project_scope_without_channel_ident_does_not_early_return_no_orders() -> None:
    interactor, _ = _make_interactor(
        candidates=[],
        fetch_map={},
        project_candidates=[OrderCandidate(order_id=ORDER_ID, post_id=POST_ID, texts=[TZ_TEXT])],
    )
    result = asyncio.run(
        interactor(
            VerifyAndPublishPostDtoInput(
                user_id=USER_ID,
                telegram_id=1,
                submission=PostSubmissionInput(
                    channel_ident=None,
                    channel_username=None,
                    post_url="",
                    text=TZ_TEXT,
                ),
                project_id=PROJECT_ID,
            ),
        ),
    )
    assert isinstance(result, Success)
    call_kwargs = interactor.match_interactor.read_gateway.read_today_order_candidates_by_project.await_args.kwargs
    assert call_kwargs["channel_ident"] is None
    assert call_kwargs["project_id"] == PROJECT_ID
