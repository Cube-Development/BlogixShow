from structlog import get_logger

from aiogram import Router
from aiogram.types import Message
from dishka import FromDishka

from advertiser_blogger.application.common.application.group_notification.group_outbox import GroupOutbox
from advertiser_blogger.application.interactors_bot.match_and_attach_post.dto import (
    MatchAndAttachPostDtoInput, MatchSuccess,
)
from advertiser_blogger.application.interactors_bot.match_and_attach_post.use_case import (
    MatchAndAttachPostInteractor,
)
from advertiser_blogger.domain.record.common.entities.group_outbox import PostVerifySource
from advertiser_blogger.infrastructure.db.repositories.read import ReadRepository
from advertiser_blogger.infrastructure.db.repositories.record import UserRepository
from advertiser_blogger.presentation.bot.common.extract_channel_post_submission import (
    extract_channel_post_submission,
)
from configuration.common import CommonConfig

logger = get_logger(__name__)

ChannelRouter = Router(name="ChannelRouter")


@ChannelRouter.channel_post()
async def on_channel_post(
        message: Message,
        interactor: FromDishka[MatchAndAttachPostInteractor],
        read_repository: FromDishka[ReadRepository],
        group_outbox: FromDishka[GroupOutbox],
        record_gateway: FromDishka[UserRepository],
        config: FromDishka[CommonConfig],
) -> None:
    submission = extract_channel_post_submission(message=message)
    if not submission.text:
        return

    channel_ident = await read_repository.resolve_channel_ident_in_db(
        channel_ident=submission.channel_ident,
    )
    if channel_ident is None:
        await read_repository.close()
        return

    owner_id = await read_repository.get_channel_owner_by_channel_ident(channel_ident=channel_ident)
    await read_repository.close()
    if owner_id is None:
        return

    telegram_id = config.bot.channel_post_telegram_id

    result = await interactor(
        data=MatchAndAttachPostDtoInput(
            source="channel_bot",
            user_id=owner_id,
            telegram_id=telegram_id,
            post_url=submission.post_url,
            submitted_text=submission.text,
            channel_ident=channel_ident,
        ),
    )
    if isinstance(result, MatchSuccess):
        logger.info(
            "channel post matched", order_id=result.order_id, score=result.score,
            post_url=submission.post_url, telegram_id=telegram_id,
        )
        channel_id = await record_gateway.get_channel_id_from_order_id(order_id=result.order_id)
        channel = await record_gateway.get_channel_by_id(channel_id=channel_id) if channel_id else None
        post_date = await record_gateway.get_post_date(order_id=result.order_id)
        time_interval = await record_gateway.get_post_time_interval(order_id=result.order_id)
        publish_date = post_date.strftime("%d.%m.%Y") if post_date else ""
        publish_time = (
            f"{time_interval.time_from.strftime('%H:%M')} - {time_interval.time_to.strftime('%H:%M')}"
            if time_interval else ""
        )
        await group_outbox.auto_posting_ok(
            order_id=result.order_id,
            channel_url=channel.channel.url if channel else "",
            publish_date=publish_date,
            publish_time=publish_time,
            score=result.score,
            post_url=submission.post_url,
            source=PostVerifySource.channel_bot.value,
        )
        await record_gateway.commit()
        await record_gateway.close()
