from advertiser_blogger.application.common.application.notification.notification import NotificationOutbox
from advertiser_blogger.domain.record.order.services.project_service import ProjectService
from advertiser_blogger.domain.record.order.entities.order import TimeInterval
from typing import Optional
from advertiser_blogger.application.common.exceptions import AppResource
from advertiser_blogger.domain.record.common.entities.event import CommonEventSubject
from uuid import UUID
from advertiser_blogger.domain.record.channel.constants import PlatformType
from datetime import datetime, timedelta, date

from advertiser_blogger.application.common.application.user_events.events import UserEventsCircle
from advertiser_blogger.application.common.constants import Timezone
from advertiser_blogger.application.common.use_case import UseCase
from advertiser_blogger.application.interactors_bot.publish_post_broadcast.dto import (
    PublishPostBroadcastDtoInput, PublishPostBroadcastDtoOutput, PublishPostFailureReason,
    PublishPostResult,
)
from advertiser_blogger.application.interactors_bot.publish_post_broadcast.interface import (
    DbGateway, SocialGateway,
)
from advertiser_blogger.domain.record.channel.entities.channel import ChannelFormatVO
from advertiser_blogger.domain.record.common.entities.event import EventSubject
from advertiser_blogger.domain.record.common.services.event_service import EventService
from advertiser_blogger.domain.record.order.constants import OrderStatus
from advertiser_blogger.domain.record.order.services.post_not_deleted_check_scheduler import (
    build_post_not_deleted_check_events,
)
from advertiser_blogger.domain.record.order.services.post_service import PostService


class PublishPostBroadcastInteractor(UseCase[PublishPostBroadcastDtoInput, PublishPostBroadcastDtoOutput]):
    def __init__(
            self, db_gateway: DbGateway, post_service: PostService, event_service: EventService,
            circle: UserEventsCircle, notification_gateway: NotificationOutbox,
            social_gateway: SocialGateway, project_service: ProjectService,
    ):
        self.db_gateway = db_gateway
        self.post_service = post_service
        self.event_service = event_service
        self.circle = circle
        self.notification_gateway = notification_gateway
        self.social_gateway = social_gateway
        self.project_service = project_service

    async def __call__(self, data: PublishPostBroadcastDtoInput) -> PublishPostBroadcastDtoOutput:
        results: list[PublishPostResult] = []
        for post in data.posts:
            result = PublishPostResult(order_id=post.order_id, post_url=post.post_url, success=False)
            order = await self.db_gateway.get_blogger_order(order_id=post.order_id)
            if order is None:
                result.reason = PublishPostFailureReason.order_not_found
                results.append(result)
                continue
            channel_owner = await self.db_gateway.get_executor(order_id=order.id)
            if channel_owner is None:
                result.reason = PublishPostFailureReason.channel_not_found
                results.append(result)
                continue
            elif channel_owner != data.user_id:
                result.reason = PublishPostFailureReason.access_denied
                results.append(result)
                continue
            if order.status not in [OrderStatus.wait, OrderStatus.in_progress]:
                result.reason = PublishPostFailureReason.invalid_status
                results.append(result)
                continue
            published_post = await self.db_gateway.is_exist_post(order_id=post.order_id)
            if published_post is not None:
                result.reason = PublishPostFailureReason.already_published
                results.append(result)
                continue
            current_date = datetime.utcnow() + timedelta(hours=Timezone.TASHKENT.value)
            replace_error = await self.replace_date(order_id=post.order_id, current_datetime=current_date)
            if replace_error is not None:
                result.reason = replace_error
                results.append(result)
                continue
            post_date = await self.db_gateway.get_post_date(order_id=post.order_id)
            time_interval = await self.db_gateway.get_post_time_interval(order_id=post.order_id)
            if post_date is None or time_interval is None:
                result.reason = PublishPostFailureReason.date_or_time_not_setup
                results.append(result)
                continue
            post_time_from = datetime(
                year=post_date.year, month=post_date.month, day=post_date.day,
                hour=time_interval.time_from.hour, minute=time_interval.time_from.minute,
            ) - timedelta(hours=1)
            post_time_to = datetime(
                year=post_date.year, month=post_date.month, day=post_date.day,
                hour=time_interval.time_to.hour, minute=time_interval.time_to.minute,
            ) + timedelta(minutes=30)
            if not (post_time_from <= current_date <= post_time_to):
                result.reason = PublishPostFailureReason.outside_time_window
                results.append(result)
                continue
            platform = await self.db_gateway.get_platform_from_order(order_id=order.id)
            post_info = await self.social_gateway.get_post_info(post_url=post.post_url, platform=platform)
            if post_info is None:
                published_date = datetime(
                    year=post_date.year, month=post_date.month, day=post_date.day,
                    hour=time_interval.time_from.hour, minute=time_interval.time_from.minute,
                )
            else:
                published_date = post_info.published
            published_post = self.post_service.publish_post(
                order_id=post.order_id, url=post.post_url, published=published_date,
            )
            await self.db_gateway.create_published_post(post=published_post)
            await self.db_gateway.flush()
            if platform == PlatformType.youtube:
                screenshot = post.post_url
                await self.db_gateway.attach_screenshot(
                    publish_id=published_post.id, file=screenshot,
                )
            else:
                worker_id = None if post_info is None else post_info.worker_id
                screenshot_event = self.event_service.create_screenshot_event(
                        subject=CommonEventSubject.order_screenshot,
                        payload={
                            "order_id": order.id,
                            "worker_id": worker_id,
                        },
                        resource_id=order.id, resource_type=AppResource.ORDER,
                    )
                await self.db_gateway.create_common_event(event=screenshot_event)
                await self.db_gateway.flush()
                for i in screenshot_event.retries:
                    await self.db_gateway.create_common_retry(retry=i)
            await self.db_gateway.attach_telegram_id_to_order(
                    order_id=post.order_id, telegram_id=data.telegram_id,
                )
            await self.db_gateway.change_order_status(order_id=post.order_id, status=OrderStatus.post_review)
            user = await self.db_gateway.get_user_by_project_id(project_id=order.project_id)
            format = ChannelFormatVO(name=order.format, price=order.price)
            event_to_accept_project = self.event_service.create_event(
                subject=EventSubject.order_advertiser_auto_accept, payload={"order_id": order.id},
                must_delivered_at=datetime.utcnow() + timedelta(hours=format.durable),
            )
            await self.db_gateway.create_event(event=event_to_accept_project)
            await self.circle.create_publish_post(project_id=order.project_id, order_id=order.id)
            order_info = await self.db_gateway.get_project_order_and_channel_status(order_id=post.order_id)
            await self.notification_gateway.post_published(
                user_id=user.id, email_address=user.email, language=user.language,
                project_id=order.project_id, order_id=post.order_id, channel_name=order_info.channel_name,
            )
            await self._schedule_post_not_deleted_checks(
                order_id=order.id, published_at=published_date,
            )
            await self.db_gateway.commit()
            results.append(PublishPostResult(
                order_id=post.order_id, post_url=post.post_url, success=True,
            ))
        published = [result for result in results if result.success]
        if published:
            observe_event = self.event_service.create_delayed_common_event(
                subject=CommonEventSubject.orders_observe,
                payload={},
                resource_id=published[0].order_id,
                resource_type=AppResource.ORDER,
                must_delivered_at=datetime.utcnow(),
            )
            await self.db_gateway.create_common_event(event=observe_event)
            await self.db_gateway.flush()
            for retry in observe_event.retries:
                await self.db_gateway.create_common_retry(retry=retry)
            await self.db_gateway.commit()
        return PublishPostBroadcastDtoOutput(results=results)

    async def _schedule_post_not_deleted_checks(
            self, order_id: UUID, published_at: datetime,
    ) -> None:
        for event in build_post_not_deleted_check_events(
            order_id=order_id, event_service=self.event_service, published_at=published_at,
        ):
            await self.db_gateway.create_common_event(event=event)
            await self.db_gateway.flush()
            for retry in event.retries:
                await self.db_gateway.create_common_retry(retry=retry)

    async def replace_date(
            self, order_id: UUID, current_datetime: datetime,
    ) -> Optional[PublishPostFailureReason]:
        order_date = await self.db_gateway.get_order_date(order_id=order_id)
        time_interval = await self.db_gateway.get_post_time_interval(order_id=order_id)
        order_dates = await self.db_gateway.get_order_dates(order_id=order_id)
        check = await self.check_possible_accept_order(
            order_id=order_id, order_date=order_date, time_interval=time_interval,
            current_datetime=current_datetime,
        )
        if not check:
            await self.db_gateway.close()
            return PublishPostFailureReason.order_expired
        if order_date is None:
            for d in order_dates:
                date_from = datetime(
                    year=d.date_from.year, month=d.date_from.month, day=d.date_from.day,
                    hour=time_interval.time_from.hour, minute=time_interval.time_from.minute,
                ) - timedelta(hours=1)
                date_to = datetime(
                    year=d.date_to.year, month=d.date_to.month, day=d.date_to.day,
                    hour=time_interval.time_to.hour, minute=time_interval.time_to.minute,
                ) + timedelta(minutes=30)
                if date_from <= current_datetime <= date_to:
                    break
            else:
                await self.db_gateway.close()
                return PublishPostFailureReason.date_out_of_interval
            order_date_rec = self.project_service.create_post_date(
                order_id=order_id, post_date=(current_datetime - timedelta(minutes=30)).date(),
            )
            order_date = order_date_rec.date
            await self.db_gateway.delete_date_intervals(order_id=order_id)
            await self.db_gateway.create_order_date(order_date=order_date_rec)
            await self.db_gateway.flush()
        return None

    async def check_possible_accept_order(
            self, order_id: UUID, order_date: Optional[date], time_interval: TimeInterval,
            current_datetime: datetime,
    ) -> bool:
        order_date_interval_max = await self.db_gateway.get_order_date_interval_max(order_id=order_id)
        if order_date is not None:
            to_ = datetime(
                year=order_date.year, month=order_date.month, day=order_date.day,
                hour=time_interval.time_to.hour, minute=time_interval.time_to.minute,
            ) + timedelta(minutes=30)
            if current_datetime > to_:
                await self.db_gateway.close()
                return False
        else:
            datetime_max = datetime(
                year=order_date_interval_max.year, month=order_date_interval_max.month, day=order_date_interval_max.day,
                hour=time_interval.time_to.hour, minute=time_interval.time_to.minute,
            ) + timedelta(minutes=30)
            if order_date_interval_max is not None:
                if current_datetime > datetime_max:
                    await self.db_gateway.close()
                    return False
                else:
                    return True
        return True
