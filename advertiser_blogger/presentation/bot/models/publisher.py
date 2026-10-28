from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from advertiser_blogger.domain.read.common.entities.date_time import DatePeriod, TimePeriod
from advertiser_blogger.domain.record.order.constants import OrderStatus


class ShowOrderModel(BaseModel):
    id: UUID
    name: str
    url: str
    format: str
    must_publish_date: DatePeriod | date
    must_publish_time: TimePeriod
    published: Optional[datetime]
    published_post: Optional[str]
    post_url: Optional[str]
    status: OrderStatus


class PublisherProject(BaseModel):
    orders: list[ShowOrderModel]