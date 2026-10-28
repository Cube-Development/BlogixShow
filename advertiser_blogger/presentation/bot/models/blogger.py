from uuid import UUID

from pydantic import BaseModel


class PublishOrderData(BaseModel):
    id: int
    order_id: UUID


class BloggerPublishData(BaseModel):
    message_id: int
    post_id: UUID
    orders: list[PublishOrderData]


class BloggerPublishDataSet(BaseModel):
    project_id: UUID
    posts: list[BloggerPublishData]