from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import (
    CreativeKind,
)
from advertiser_blogger.domain.record.channel.constants import Format


class ScheduleSource(str, Enum):
    user_defined = "user_defined"
    default_generated = "default_generated"


class PublishMode(str, Enum):
    copy = "copy"
    forward = "forward"


class ChannelRefStatus(str, Enum):
    found = "found"
    unknown = "unknown"
    invalid = "invalid"


@dataclass
class ParsedScheduleFragments:
    date: Optional[str] = None  # absolute dd.mm.yyyy or relative today/tomorrow/day_after
    start_time: Optional[str] = None  # HH:MM or hour "17"
    end_time: Optional[str] = None
    relative_day: Optional[str] = None  # today | tomorrow | day_after


@dataclass
class ParsedProjectReply:
    project_name: Optional[str] = None
    comment: Optional[str] = None
    schedule: ParsedScheduleFragments = field(default_factory=ParsedScheduleFragments)
    channel_queries: list[str] = field(default_factory=list)
    unmatched_lines: list[str] = field(default_factory=list)


@dataclass
class ProjectSchedule:
    start_at: datetime
    end_at: datetime
    source: ScheduleSource


@dataclass
class BotChannelRef:
    status: ChannelRefStatus
    query_raw: str
    channel_id: Optional[UUID] = None
    display_name: Optional[str] = None
    url: Optional[str] = None
    format: Optional[Format] = None
    is_swap: bool = False
    comment: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    schedule_source: Optional[ScheduleSource] = None


@dataclass
class BotMediaPart:
    content_type: str  # photo | video | document | text
    file_id: Optional[str] = None
    text: Optional[str] = None


@dataclass
class BotPostDraft:
    local_id: str
    text: Optional[str] = None
    media: list[BotMediaPart] = field(default_factory=list)
    channels: list[BotChannelRef] = field(default_factory=list)
    source_message_ids: list[int] = field(default_factory=list)
    bot_message_ids: list[int] = field(default_factory=list)
    media_group_id: Optional[str] = None
    kind: CreativeKind = CreativeKind.media


@dataclass
class BotProjectDraft:
    draft_id: str
    user_id: UUID
    telegram_id: int
    project_name: Optional[str] = None
    comment: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    schedule_source: Optional[ScheduleSource] = None
    posts: list[BotPostDraft] = field(default_factory=list)
    active_post_id: Optional[str] = None
    # Real backend common only when draft has exactly one post; otherwise None.
    common_post_id: Optional[str] = None
    publish_mode: Optional[PublishMode] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "user_id": str(self.user_id),
            "telegram_id": self.telegram_id,
            "project_name": self.project_name,
            "comment": self.comment,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "schedule_source": self.schedule_source.value if self.schedule_source else None,
            "active_post_id": self.active_post_id,
            "common_post_id": self.common_post_id,
            "publish_mode": self.publish_mode.value if self.publish_mode else None,
            "posts": [
                {
                    "local_id": p.local_id,
                    "text": p.text,
                    "media_group_id": p.media_group_id,
                    "source_message_ids": p.source_message_ids,
                    "bot_message_ids": p.bot_message_ids,
                    "kind": p.kind.value if isinstance(p.kind, CreativeKind) else (p.kind or CreativeKind.media.value),
                    "media": [
                        {
                            "content_type": m.content_type,
                            "file_id": m.file_id,
                            "text": m.text,
                        }
                        for m in p.media
                    ],
                    "channels": [
                        {
                            "status": c.status.value,
                            "query_raw": c.query_raw,
                            "channel_id": str(c.channel_id) if c.channel_id else None,
                            "display_name": c.display_name,
                            "url": c.url,
                            "format": int(c.format) if c.format is not None else None,
                            "is_swap": c.is_swap,
                            "comment": c.comment,
                            "start_at": c.start_at.isoformat() if c.start_at else None,
                            "end_at": c.end_at.isoformat() if c.end_at else None,
                            "schedule_source": (
                                c.schedule_source.value if c.schedule_source else None
                            ),
                        }
                        for c in p.channels
                    ],
                }
                for p in self.posts
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BotProjectDraft:
        posts: list[BotPostDraft] = []
        for p in data.get("posts") or []:
            channels = [
                BotChannelRef(
                    status=ChannelRefStatus(c["status"]),
                    query_raw=c["query_raw"],
                    channel_id=UUID(c["channel_id"]) if c.get("channel_id") else None,
                    display_name=c.get("display_name"),
                    url=c.get("url"),
                    format=Format(c["format"]) if c.get("format") is not None else None,
                    is_swap=bool(c.get("is_swap", False)),
                    comment=c.get("comment"),
                    start_at=(
                        datetime.fromisoformat(c["start_at"]) if c.get("start_at") else None
                    ),
                    end_at=datetime.fromisoformat(c["end_at"]) if c.get("end_at") else None,
                    schedule_source=(
                        ScheduleSource(c["schedule_source"])
                        if c.get("schedule_source")
                        else None
                    ),
                )
                for c in p.get("channels") or []
            ]
            media = [
                BotMediaPart(
                    content_type=m["content_type"],
                    file_id=m.get("file_id"),
                    text=m.get("text"),
                )
                for m in p.get("media") or []
            ]
            posts.append(
                BotPostDraft(
                    local_id=p["local_id"],
                    text=p.get("text"),
                    media=media,
                    channels=channels,
                    source_message_ids=list(p.get("source_message_ids") or []),
                    bot_message_ids=list(p.get("bot_message_ids") or []),
                    media_group_id=p.get("media_group_id"),
                    kind=CreativeKind(p["kind"]) if p.get("kind") else CreativeKind.media,
                )
            )
        return cls(
            draft_id=data["draft_id"],
            user_id=UUID(data["user_id"]),
            telegram_id=int(data["telegram_id"]),
            project_name=data.get("project_name"),
            comment=data.get("comment"),
            start_at=datetime.fromisoformat(data["start_at"]) if data.get("start_at") else None,
            end_at=datetime.fromisoformat(data["end_at"]) if data.get("end_at") else None,
            schedule_source=(
                ScheduleSource(data["schedule_source"]) if data.get("schedule_source") else None
            ),
            posts=posts,
            active_post_id=data.get("active_post_id"),
            common_post_id=data.get("common_post_id"),
            publish_mode=_publish_mode_from_dict(data, posts),
        )


def _publish_mode_from_dict(data: dict[str, Any], posts: list[BotPostDraft]) -> PublishMode | None:
    raw = data.get("publish_mode")
    if raw:
        try:
            return PublishMode(raw)
        except ValueError:
            pass
    if posts:
        return PublishMode.forward
    return None


def uses_bot_mirror(draft: BotProjectDraft) -> bool:
    if draft.publish_mode is PublishMode.copy:
        return False
    if draft.publish_mode is PublishMode.forward:
        return True
    return bool(draft.posts)


def resolve_publish_mode(mode: PublishMode | None) -> PublishMode:
    return mode or PublishMode.forward
