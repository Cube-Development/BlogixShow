from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from advertiser_blogger.application.common.application.post.post_convert import FileObject
from advertiser_blogger.application.common.exceptions.application_error import AccessDenied, OrderNotFound
from advertiser_blogger.application.interactors_bot.collect_createorder_post.dto import (
    CollectCreateorderAcceptInput,
)
from advertiser_blogger.application.interactors_bot.collect_createorder_post.use_case import (
    CollectCreateorderAcceptPost,
)
from advertiser_blogger.application.interactors_bot.project_create.models import BotPostDraft
from advertiser_blogger.application.read.read_post.dto import ReadPostDtoInput
from advertiser_blogger.application.read.read_post.use_case import ReadPostInteractor
from advertiser_blogger.application.record.create_post_custom_orders.use_case import CreatePostCustomOrders
from advertiser_blogger.domain.read.constants import Role
from advertiser_blogger.domain.read.order.entities.order import PostView
from advertiser_blogger.domain.read.post.entities import FileView
from advertiser_blogger.domain.record.channel.constants import Format, PlatformType
from advertiser_blogger.domain.record.common.services.event_service import EventService
from advertiser_blogger.domain.record.order.constants import ContentType, OrderStatus, PostMatchType, ProjectStatus
from advertiser_blogger.domain.record.order.entities.order import Project
from advertiser_blogger.domain.record.order.services.post_service import PostService
from advertiser_blogger.domain.record.order.services.project_service import ProjectService


def run(coro):
    return asyncio.run(coro)


class _Owner:
    def __init__(self, user_id, role=Role.advertiser):
        self.id = user_id
        self.role = role


class _ObjStorage:
    async def presigned_get(self, key: str) -> str:
        return key


class CollectPersistenceGateway:
    """In-memory record+read gateway for Collect → CreatePostCustomOrders parity."""

    def __init__(
            self,
            *,
            project: Project,
            owner,
            project_order_ids: list[UUID],
            matches: list[dict] | None = None,
            posts: dict[UUID, UUID] | None = None,
            tariff_id=None,
    ):
        self.project = project
        self.owner = owner
        self.project_order_ids = list(project_order_ids)
        self.matches = list(matches or [])
        self.posts = dict(posts or {})
        self.post_texts: dict[UUID, list[str]] = {}
        self.tariff_id = tariff_id
        self.created_posts: list[dict] = []
        self.removed_posts: list[UUID] = []
        self.order_status: dict[UUID, OrderStatus] = {}
        self.events = []
        self.committed = False
        self.closed = False

    async def get_project(self, project_id):
        return self.project if project_id == self.project.id else None

    async def get_user_by_id(self, user_id):
        return self.owner if user_id == self.owner.id else None

    async def get_tariff_id_by_project_id(self, project_id):
        return self.tariff_id

    async def exists_orders_in_project(self, project_id, orders):
        if project_id != self.project.id:
            return []
        return [order_id for order_id in orders if order_id in self.project_order_ids]

    async def get_project_order_ids(self, project_id):
        if project_id != self.project.id:
            return []
        return list(self.project_order_ids)

    async def create_post(self, id, project_id, match_type):
        self.posts[id] = project_id
        self.created_posts.append({"id": id, "project_id": project_id, "match_type": match_type})

    async def flush(self):
        return None

    async def create_post_identificator(self, post_id):
        return None

    async def create_post_comment(self, id, post_id, comment):
        return None

    async def create_post_text(self, id, post_id, content, content_type):
        self.post_texts.setdefault(post_id, []).append(content)

    async def create_post_button(self, id, post_id, content, url, content_type):
        return None

    async def create_post_content(self, id, post_id, content, name, content_type):
        return None

    async def remove_order_match(self, project_id, order_id):
        self.matches = [
            match for match in self.matches
            if not (match["project_id"] == project_id and match["order_id"] == order_id)
        ]

    async def create_order_match(self, match):
        self.matches.append({
            "id": match.id,
            "project_id": match.project_id,
            "order_id": match.order_id,
            "post_id": match.post_id,
        })

    async def change_order_status(self, order_id, status):
        self.order_status[order_id] = status

    async def get_project_post_id(self, project_id):
        return [post_id for post_id, owner_project in self.posts.items() if owner_project == project_id]

    async def get_matched_orders(self, project_id, post_id):
        return sum(
            1 for match in self.matches
            if match["project_id"] == project_id and match["post_id"] == post_id
        )

    async def remove_post(self, post_id):
        self.posts.pop(post_id, None)
        self.post_texts.pop(post_id, None)
        self.removed_posts.append(post_id)
        self.matches = [match for match in self.matches if match["post_id"] != post_id]

    async def create_event(self, event):
        self.events.append(event)

    async def commit(self):
        self.committed = True

    async def close(self):
        self.closed = True

    async def read_post(self, order_id: UUID) -> PostView | None:
        # Same join as GET /order/post?order_id=: MatchPostChannel ⋈ Post ⋈ Order, no time interval.
        match = next((item for item in self.matches if item["order_id"] == order_id), None)
        if match is None:
            return None
        post_id = match["post_id"]
        if post_id not in self.posts:
            return None
        return PostView(
            id=post_id,
            post_ident=1,
            platform=PlatformType.telegram,
            format=Format.telegram_24,
            comment=None,
            files=[],
            buttons=[],
            text=[
                FileView(content_type=ContentType.text, content=content, name=None)
                for content in self.post_texts.get(post_id, [])
            ],
        )


def _project(user_id) -> Project:
    now = datetime.utcnow()
    return Project(
        id=uuid4(), user_id=user_id, name="p", status=ProjectStatus.saved, created=now, updated=now,
    )


def _files():
    return [FileObject(content_type=ContentType.text, content="<p>https://t.me/tz/1</p>", name=None)]


def _accept(gateway) -> CollectCreateorderAcceptPost:
    return CollectCreateorderAcceptPost(
        auth_gateway=gateway,
        media_uploader=_uploader(),
        create_post_custom_orders=CreatePostCustomOrders(
            db_gateway=gateway,
            project_service=ProjectService(),
            post_service=PostService(),
            event_service=EventService(),
        ),
    )


def _uploader():
    async def upload(post, *, telegram_chat_id, publish_mode):
        return _files()

    return upload


def _read(gateway) -> ReadPostInteractor:
    return ReadPostInteractor(
        db_gateway=gateway,
        obj_storage=_ObjStorage(),
        post_service=PostService(),
    )


def _input(*, user_id, project_id, order_id):
    return CollectCreateorderAcceptInput(
        user_id=user_id,
        telegram_chat_id=1,
        project_id=project_id,
        order_id=order_id,
        post=BotPostDraft(local_id="x", source_message_ids=[1]),
    )


def _matches_by_order(gateway) -> dict[UUID, UUID]:
    return {match["order_id"]: match["post_id"] for match in gateway.matches}


def test_unique_persists_match_visible_to_get_order_post() -> None:
    user_id = uuid4()
    owner = _Owner(user_id)
    project = _project(user_id)
    order_id = uuid4()
    other_order = uuid4()
    gateway = CollectPersistenceGateway(
        project=project,
        owner=owner,
        project_order_ids=[order_id, other_order],
    )

    run(_accept(gateway)(data=_input(user_id=user_id, project_id=project.id, order_id=order_id)))

    assert gateway.committed is True
    assert len(gateway.created_posts) == 1
    new_post = gateway.created_posts[0]["id"]
    assert gateway.created_posts[0]["project_id"] == project.id
    assert gateway.created_posts[0]["match_type"] == PostMatchType.individual
    assert _matches_by_order(gateway) == {order_id: new_post}
    assert gateway.matches[0]["project_id"] == project.id
    assert gateway.order_status[order_id] == OrderStatus.post_matched
    assert other_order not in _matches_by_order(gateway)

    viewed = run(_read(gateway)(data=ReadPostDtoInput(order_id=order_id)))
    assert viewed.id == new_post


def test_universal_persists_matches_for_all_project_orders() -> None:
    user_id = uuid4()
    owner = _Owner(user_id)
    project = _project(user_id)
    order_a, order_b = uuid4(), uuid4()
    gateway = CollectPersistenceGateway(
        project=project,
        owner=owner,
        project_order_ids=[order_a, order_b],
    )

    run(_accept(gateway)(data=_input(user_id=user_id, project_id=project.id, order_id=None)))

    assert gateway.committed is True
    new_post = gateway.created_posts[0]["id"]
    assert gateway.created_posts[0]["match_type"] == PostMatchType.universal
    assert _matches_by_order(gateway) == {order_a: new_post, order_b: new_post}
    assert all(match["project_id"] == project.id for match in gateway.matches)
    assert gateway.order_status[order_a] == OrderStatus.post_matched
    assert gateway.order_status[order_b] == OrderStatus.post_matched

    viewed_a = run(_read(gateway)(data=ReadPostDtoInput(order_id=order_a)))
    viewed_b = run(_read(gateway)(data=ReadPostDtoInput(order_id=order_b)))
    assert viewed_a.id == new_post
    assert viewed_b.id == new_post


def test_unique_overwrite_removes_old_match_and_keeps_shared_post() -> None:
    user_id = uuid4()
    owner = _Owner(user_id)
    project = _project(user_id)
    order_a, order_b = uuid4(), uuid4()
    old_post = uuid4()
    gateway = CollectPersistenceGateway(
        project=project,
        owner=owner,
        project_order_ids=[order_a, order_b],
        posts={old_post: project.id},
        matches=[
            {"id": uuid4(), "project_id": project.id, "order_id": order_a, "post_id": old_post},
            {"id": uuid4(), "project_id": project.id, "order_id": order_b, "post_id": old_post},
        ],
    )

    run(_accept(gateway)(data=_input(user_id=user_id, project_id=project.id, order_id=order_a)))

    new_post = gateway.created_posts[0]["id"]
    assert _matches_by_order(gateway) == {order_a: new_post, order_b: old_post}
    assert old_post not in gateway.removed_posts
    assert gateway.order_status[order_a] == OrderStatus.post_matched
    assert run(_read(gateway)(data=ReadPostDtoInput(order_id=order_a))).id == new_post
    assert run(_read(gateway)(data=ReadPostDtoInput(order_id=order_b))).id == old_post


def test_unique_overwrite_deletes_old_post_when_no_matches_left() -> None:
    user_id = uuid4()
    owner = _Owner(user_id)
    project = _project(user_id)
    order_id = uuid4()
    old_post = uuid4()
    gateway = CollectPersistenceGateway(
        project=project,
        owner=owner,
        project_order_ids=[order_id],
        posts={old_post: project.id},
        matches=[
            {"id": uuid4(), "project_id": project.id, "order_id": order_id, "post_id": old_post},
        ],
    )

    run(_accept(gateway)(data=_input(user_id=user_id, project_id=project.id, order_id=order_id)))

    new_post = gateway.created_posts[0]["id"]
    assert _matches_by_order(gateway) == {order_id: new_post}
    assert old_post in gateway.removed_posts
    assert run(_read(gateway)(data=ReadPostDtoInput(order_id=order_id))).id == new_post


def test_invalid_order_does_not_persist() -> None:
    user_id = uuid4()
    owner = _Owner(user_id)
    project = _project(user_id)
    gateway = CollectPersistenceGateway(
        project=project,
        owner=owner,
        project_order_ids=[uuid4()],
    )

    with pytest.raises(OrderNotFound):
        run(_accept(gateway)(data=_input(user_id=user_id, project_id=project.id, order_id=uuid4())))

    assert gateway.committed is False
    assert gateway.created_posts == []
    assert gateway.matches == []


def test_unauthorized_user_does_not_persist() -> None:
    owner_id = uuid4()
    stranger_id = uuid4()
    project = _project(owner_id)
    order_id = uuid4()
    gateway = CollectPersistenceGateway(
        project=project,
        owner=_Owner(stranger_id),
        project_order_ids=[order_id],
    )

    with pytest.raises(AccessDenied):
        run(_accept(gateway)(data=_input(user_id=stranger_id, project_id=project.id, order_id=order_id)))

    assert gateway.committed is False
    assert gateway.created_posts == []
    assert gateway.matches == []
