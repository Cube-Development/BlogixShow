from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from aiogram.types import Message


class RegisterResult(str, Enum):
    FIRST = "first"
    PENDING = "pending"
    FLUSH_SCHEDULED = "flush_scheduled"
    IGNORED = "ignored"


@dataclass(frozen=True)
class MessageBatch:
    chat_id: int
    messages: list[Message]
    created_at: datetime

    @property
    def received_count(self) -> int:
        return len(self.messages)
