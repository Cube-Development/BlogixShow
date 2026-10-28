from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aiogram.types import Message

from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import (
    CreativeKind,
    detect_text_creative_kind,
)
from advertiser_blogger.application.interactors_bot.project_create.parser import (
    looks_like_project_metadata,
    parse_project_reply,
)


class PairingState(str, Enum):
    IDLE = "idle"
    WAITING_CHANNEL = "waiting_channel"


class PairingEvent(str, Enum):
    MEDIA = "media"
    CHANNEL_ONLY = "channel_only"
    RICH_METADATA = "rich_metadata"
    IGNORE = "ignore"


class PairingActionKind(str, Enum):
    CREATE_POST = "create_post"
    BIND_CHANNEL = "bind_channel"
    APPLY_RICH_METADATA = "apply_rich_metadata"
    IGNORE = "ignore"


@dataclass(frozen=True)
class PairingAction:
    kind: PairingActionKind
    message: Message
    bind_to_message_id: int | None = None


def message_has_media(message: Message) -> bool:
    return bool(
        getattr(message, "video", None)
        or getattr(message, "photo", None)
        or getattr(message, "document", None)
        or getattr(message, "animation", None)
    )


def is_channel_only_metadata(text: str) -> bool:
    parsed = parse_project_reply(text)
    if not parsed.channel_queries:
        return False
    schedule = parsed.schedule
    return not (
        parsed.project_name
        or parsed.comment
        or schedule.date
        or schedule.start_time
        or schedule.end_time
        or schedule.relative_day
    )


def is_text_creative_message(text: str) -> bool:
    """True when plain text should create a post (button / repost / non-metadata text)."""
    kind = detect_text_creative_kind(text)
    if kind is None:
        return False
    if kind in (CreativeKind.button, CreativeKind.repost):
        return True
    return kind is CreativeKind.text and not looks_like_project_metadata(text)


def classify_message(message: Message) -> PairingEvent:
    has_media = message_has_media(message)
    text = message.text or message.caption or ""
    if has_media:
        return PairingEvent.MEDIA
    if is_text_creative_message(text):
        return PairingEvent.MEDIA
    if not looks_like_project_metadata(text):
        return PairingEvent.IGNORE
    if is_channel_only_metadata(text):
        return PairingEvent.CHANNEL_ONLY
    return PairingEvent.RICH_METADATA


class ProjectCreatePairingFSM:
    """Pairs media/text posts with following channel-only links after message_id sort."""

    def __init__(self) -> None:
        self.state = PairingState.IDLE
        self.waiting_post_message_id: int | None = None

    def restore(self, waiting_post_message_id: int) -> None:
        self.state = PairingState.WAITING_CHANNEL
        self.waiting_post_message_id = waiting_post_message_id

    def on_message(self, message: Message) -> list[PairingAction]:
        event = classify_message(message)

        if event is PairingEvent.IGNORE:
            return [PairingAction(kind=PairingActionKind.IGNORE, message=message)]

        if event is PairingEvent.RICH_METADATA:
            self.state = PairingState.IDLE
            self.waiting_post_message_id = None
            return [PairingAction(kind=PairingActionKind.APPLY_RICH_METADATA, message=message)]

        if event is PairingEvent.MEDIA:
            self.state = PairingState.WAITING_CHANNEL
            self.waiting_post_message_id = message.message_id
            return [
                PairingAction(kind=PairingActionKind.CREATE_POST, message=message),
            ]

        reply_to = _reply_to_message_id(message)
        if reply_to is not None:
            if self.waiting_post_message_id == reply_to:
                self.state = PairingState.IDLE
                self.waiting_post_message_id = None
            return [
                PairingAction(
                    kind=PairingActionKind.BIND_CHANNEL,
                    message=message,
                    bind_to_message_id=reply_to,
                ),
            ]

        if self.state is PairingState.WAITING_CHANNEL and self.waiting_post_message_id is not None:
            bind_to = self.waiting_post_message_id
            self.state = PairingState.IDLE
            self.waiting_post_message_id = None
            return [
                PairingAction(
                    kind=PairingActionKind.BIND_CHANNEL,
                    message=message,
                    bind_to_message_id=bind_to,
                ),
            ]

        return [PairingAction(kind=PairingActionKind.APPLY_RICH_METADATA, message=message)]


def _reply_to_message_id(message: Message) -> int | None:
    reply = getattr(message, "reply_to_message", None)
    if reply is None:
        return None
    mid = getattr(reply, "message_id", None)
    return int(mid) if mid is not None else None
