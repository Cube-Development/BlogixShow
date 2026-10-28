from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class AttachTgUserFromAppDtoInput:
    attach_id: UUID
    telegram_id: int
    username: Optional[str]
