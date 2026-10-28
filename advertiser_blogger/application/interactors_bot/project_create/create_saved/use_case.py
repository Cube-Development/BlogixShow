from __future__ import annotations

from structlog import get_logger
from uuid import UUID

from advertiser_blogger.application.common.application.post.post_convert import FileObject
from advertiser_blogger.application.interactors_bot.project_create.create_saved.dto import (
    CreateSavedProjectFromBotDraftInput,
    CreateSavedProjectFromBotDraftOutput,
)
from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotProjectDraft,
    ChannelRefStatus,
)
from advertiser_blogger.application.interactors_bot.project_create.resolve_channels import (
    build_swap_order_comment,
)
from advertiser_blogger.presentation.bot.common.project_create_texts import channel_comment_for_order
from advertiser_blogger.application.interactors_bot.project_create.create_project_from_cart.dto import (
    CreateProjectFromCartInput,
)
from advertiser_blogger.application.interactors_bot.project_create.create_project_from_cart.use_case import (
    CreateProjectFromCartInteractor,
)
from advertiser_blogger.application.interactors_bot.project_create.fill_common_cart.dto import (
    FillCommonCartChannel,
    FillCommonCartInput,
)
from advertiser_blogger.application.interactors_bot.project_create.fill_common_cart.use_case import (
    FillCommonCartInteractor,
)
from advertiser_blogger.application.record.add_date_interval.dto import (
    AddDateIntervalDtoInput,
    OrderDate,
)
from advertiser_blogger.application.record.add_date_interval.use_case import CreateDateIntervalInteractor
from advertiser_blogger.application.record.create_post_custom_orders.dto import CreatePostCustomOrderDtoInput
from advertiser_blogger.application.record.create_post_custom_orders.use_case import CreatePostCustomOrders
from advertiser_blogger.application.record.save_project.dto import SaveProjectDtoInput
from advertiser_blogger.application.record.save_project.use_case import SaveProjectInteractor
from advertiser_blogger.domain.record.order.constants import ContentType

logger = get_logger(__name__)


class DraftValidationError(ValueError):
    pass


class CreateSavedProjectFromBotDraft:
    """Orchestrator: validate → cart → project/orders → posts → dates → SaveProject."""

    def __init__(
            self,
            fill_common_cart: FillCommonCartInteractor,
            create_project_from_cart: CreateProjectFromCartInteractor,
            create_post_custom_orders: CreatePostCustomOrders,
            create_date_interval: CreateDateIntervalInteractor,
            save_project: SaveProjectInteractor,
            media_to_files=None,
    ):
        self.fill_common_cart = fill_common_cart
        self.create_project_from_cart = create_project_from_cart
        self.create_post_custom_orders = create_post_custom_orders
        self.create_date_interval = create_date_interval
        self.save_project = save_project
        self.media_to_files = media_to_files

    def validate_draft(self, draft: BotProjectDraft) -> None:
        if not draft.posts:
            raise DraftValidationError("no_posts")
        if draft.start_at is None or draft.end_at is None:
            raise DraftValidationError("no_schedule")
        for post in draft.posts:
            if not post.channels:
                raise DraftValidationError("post_without_channels")
            for ch in post.channels:
                if ch.status != ChannelRefStatus.found or ch.format is None or ch.channel_id is None:
                    raise DraftValidationError("bad_channels")

    async def __call__(
            self, data: CreateSavedProjectFromBotDraftInput,
    ) -> CreateSavedProjectFromBotDraftOutput:
        draft = data.draft
        self.validate_draft(draft)
        user_id = data.user_id
        logger.info(
            "bot project save started", user_id=user_id, telegram_id=draft.telegram_id,
            posts=len(draft.posts), mode=draft.publish_mode,
        )
        for idx, post in enumerate(draft.posts, start=1):
            pass

        async def cart_progress(current: int, total: int) -> None:
            await self._progress(data.on_progress, "cart", current, total)

        await self.fill_common_cart(
            data=FillCommonCartInput(
                user_id=user_id,
                channels=[
                    FillCommonCartChannel(
                        channel_id=ch.channel_id,
                        format=ch.format,
                        match=None,
                    )
                    for post in draft.posts
                    for ch in post.channels
                    if ch.channel_id is not None and ch.format is not None
                ],
                on_progress=cart_progress,
            )
        )

        async def orders_progress(current: int, total: int) -> None:
            await self._progress(data.on_progress, "orders", current, total)

        project_id: UUID | None = None
        try:
            cart_out = await self.create_project_from_cart(
                data=CreateProjectFromCartInput(
                    user_id=user_id,
                    project_name=draft.project_name,
                    on_progress=orders_progress,
                )
            )
            project_id = cart_out.project_id
            orders = cart_out.orders
        except Exception:
            logger.exception("bot project save: create cart failed", user_id=user_id)
            raise

        try:
            channel_to_order = {o.channel_id: o.id for o in orders}

            channel_by_id: dict[UUID, object] = {}
            for post in draft.posts:
                for ch in post.channels:
                    if ch.channel_id is not None:
                        channel_by_id[ch.channel_id] = ch

            posts_total = len(orders)
            posts_done = 0
            post_errors: list[str] = []
            await self._progress(data.on_progress, "posts", 0, posts_total)

            async def bump_posts(count: int) -> None:
                nonlocal posts_done
                for _ in range(count):
                    posts_done = min(posts_total, posts_done + 1)
                    await self._progress(
                        data.on_progress, "posts", posts_done, posts_total,
                    )

            for idx, post in enumerate(draft.posts, start=1):
                found_order_ids: list = []
                try:
                    found_order_ids = [
                        channel_to_order[ch.channel_id]
                        for ch in post.channels
                        if (
                            not ch.is_swap
                            and ch.channel_id is not None
                            and ch.channel_id in channel_to_order
                        )
                    ]
                    files = await self._build_files(
                        post,
                        telegram_chat_id=draft.telegram_id,
                        publish_mode=draft.publish_mode,
                    )
                    if found_order_ids:
                        post_comment = next(
                            (
                                channel_comment_for_order(ch, draft)
                                for ch in post.channels
                                if not ch.is_swap
                            ),
                            draft.comment,
                        )
                        await self.create_post_custom_orders(
                            data=CreatePostCustomOrderDtoInput(
                                user_id=user_id,
                                project_id=project_id,
                                comment=post_comment,
                                files=files,
                                orders=found_order_ids,
                            )
                        )
                        await bump_posts(len(found_order_ids))
                    for ch in post.channels:
                        if not ch.is_swap or ch.channel_id is None:
                            continue
                        order_id = channel_to_order.get(ch.channel_id)
                        if order_id is None:
                            continue
                        await self.create_post_custom_orders(
                            data=CreatePostCustomOrderDtoInput(
                                user_id=user_id,
                                project_id=project_id,
                                comment=build_swap_order_comment(ch, user_comment=draft.comment),
                                files=files,
                                orders=[order_id],
                            )
                        )
                        await bump_posts(1)
                except Exception as exc:
                    logger.exception("bot project save: post failed", project_id=project_id, local_id=post.local_id[:8])
                    post_errors.append(str(exc))

            date_payload = []
            for o in orders:
                ch = channel_by_id.get(o.channel_id)
                if ch is not None and getattr(ch, "start_at", None) and getattr(ch, "end_at", None):
                    start_at = ch.start_at
                    end_at = ch.end_at
                else:
                    start_at = draft.start_at
                    end_at = draft.end_at
                date_payload.append(
                    OrderDate(
                        order_id=o.id,
                        date=start_at.date(),
                        time_from=start_at.time().replace(tzinfo=None),
                        time_to=end_at.time().replace(tzinfo=None),
                    )
                )
            await self.create_date_interval(
                data=AddDateIntervalDtoInput(
                    user_id=user_id, project_id=project_id, orders=date_payload,
                )
            )
            await self.save_project(
                data=SaveProjectDtoInput(user_id=user_id, project_id=project_id),
            )
            logger.info("bot project saved", project_id=project_id, posts=len(draft.posts), orders=len(orders))
            if post_errors:
                return CreateSavedProjectFromBotDraftOutput(
                    project_id=project_id, partial=True, error=post_errors[0],
                )
        except Exception as exc:
            logger.exception("bot project save: post-cart steps failed", project_id=project_id)
            return CreateSavedProjectFromBotDraftOutput(
                project_id=project_id, partial=True, error=str(exc),
            )

        return CreateSavedProjectFromBotDraftOutput(project_id=project_id, partial=False)

    async def _progress(
            self,
            callback,
            phase: str,
            current: int,
            total: int,
    ) -> None:
        if callback is None:
            return
        try:
            await callback(phase, current, total)
        except Exception as exc:
            logger.warning("bot project save: progress callback failed", phase=phase, error=str(exc))

    async def _build_files(self, post, *, telegram_chat_id: int, publish_mode=None) -> list[FileObject]:
        if self.media_to_files is not None:
            return await self.media_to_files(
                post,
                telegram_chat_id=telegram_chat_id,
                publish_mode=publish_mode,
            )
        files: list[FileObject] = []
        if post.text:
            files.append(FileObject(content_type=ContentType.text, content=post.text, name=None))
        for media in post.media:
            if media.content_type == "text" and media.text:
                files.append(FileObject(content_type=ContentType.text, content=media.text, name=None))
        if not files:
            files.append(FileObject(content_type=ContentType.text, content=post.text or " ", name=None))
        return files
