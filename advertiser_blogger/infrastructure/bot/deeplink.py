from uuid import UUID

from pydantic import BaseModel

from advertiser_blogger.domain.record.order.constants import DeeplinkType, Subrole


class DeeplinkPost(BaseModel):
    order_id: UUID


class AttachUser(BaseModel):
    attach_id: UUID


class AttachActor(BaseModel):
    project_id: UUID
    subrole: Subrole


class DeeplinkData(BaseModel):
    id: UUID
    type: DeeplinkType
    payload: DeeplinkPost | AttachUser | AttachActor