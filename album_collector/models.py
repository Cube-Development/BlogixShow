from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RegisterResult(str, Enum):
    PENDING = "pending"
    FLUSH_SCHEDULED = "flush_scheduled"
    IGNORED = "ignored"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class AlbumPart:
    update_id: int
    chat_id: int
    message_id: int
    file_id: str
    file_unique_id: str | None
    media_type: str
    caption: str | None
    date: datetime
    is_forward: bool = False
    forward_chat_id: int | None = None
    forward_chat_username: str | None = None
    forward_message_id: int | None = None
    forward_date: datetime | None = None


@dataclass
class AggregatedAlbum:
    media_group_id: str
    chat_id: int
    user_id: int
    parts: list[AlbumPart] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def caption(self) -> str | None:
        for part in sorted(self.parts, key=lambda item: item.message_id):
            if part.caption:
                return part.caption
        return None

    @property
    def primary_message_id(self) -> int | None:
        if not self.parts:
            return None
        for part in sorted(self.parts, key=lambda item: item.message_id):
            if part.caption:
                return part.message_id
        return min(self.parts, key=lambda item: item.message_id).message_id

    @property
    def forward_part(self) -> AlbumPart | None:
        for part in sorted(self.parts, key=lambda item: item.message_id):
            if part.is_forward:
                return part
        return None
