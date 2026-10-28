from dataclasses import dataclass
from datetime import date
from typing import Optional
from uuid import UUID

from advertiser_blogger.domain.read.order.entities.order import ButtonView, MatchPostOrderView
from advertiser_blogger.domain.read.post.entities import FileViewWithUrl
from advertiser_blogger.domain.record.channel.constants import PlatformType
from advertiser_blogger.domain.record.order.constants import PostType, PostMatchType


@dataclass
class ReadOrdersBloggerDtoInput:
    project_id: UUID
    page: int
    user_id: UUID
    elements_on_page: Optional[int]
    only_in_progress: bool = None
    on_date: Optional[date] = None


@dataclass
class ProjectPostBlogger:
    id: UUID
    match_type: PostMatchType
    orders: list[MatchPostOrderView]
    platform: PlatformType
    post_type: PostType
    comment: Optional[str]
    files: list[FileViewWithUrl]


@dataclass
class ReadOrdersBloggerDtoOutput:
    page: int
    elements: int
    posts: list[ProjectPostBlogger]
    completed: bool