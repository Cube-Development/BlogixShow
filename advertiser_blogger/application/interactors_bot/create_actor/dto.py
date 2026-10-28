from dataclasses import dataclass
from uuid import UUID

from advertiser_blogger.domain.record.order.constants import Subrole


@dataclass
class CreateActorDtoInput:
    project_id: UUID
    subrole: Subrole
    telegram_id: int
