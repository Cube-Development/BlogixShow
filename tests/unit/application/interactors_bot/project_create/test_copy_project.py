import asyncio
from copy import deepcopy
from datetime import date, datetime, time
from uuid import uuid4

import pytest

from advertiser_blogger.application.common.exceptions.application_error import (
    AccessDenied,
    CalendarDayIsBusy,
    DateOrTimeNotSetup,
    EmptyProjectCart,
)
from advertiser_blogger.application.interactors_bot.project_create.copy_project.date_resolver import (
    resolve_clone_date,
    resolve_clone_interval,
)
from advertiser_blogger.application.interactors_bot.project_create.copy_project.dto import CopyProjectInput
from advertiser_blogger.application.interactors_bot.project_create.copy_project.use_case import CopyProjectInteractor
from advertiser_blogger.domain.record.cart.services.project_cart_service import ProjectCartService
from advertiser_blogger.domain.record.channel.constants import ChannelStatus, Format
from advertiser_blogger.domain.record.channel.entities.pricing import ChannelFormatPrices
from advertiser_blogger.domain.record.order.constants import (
    ContentType,
    OrderCrushType,
    OrderStatus,
    PostMatchType,
    ProjectStatus,
)
from advertiser_blogger.domain.record.order.entities.order import (
    Button,
    DateInterval,
    File,
    Order,
    Post,
    Project,
    TimeInterval,
)
from advertiser_blogger.domain.record.order.services.post_service import PostService
from advertiser_blogger.domain.record.order.services.project_service import ProjectService
from advertiser_blogger.domain.record.wallet.services.wallet import WalletService


def run(coro):
    return asyncio.run(coro)


class FakeGateway:
    def __init__(self, *, source_project, source_orders, channel_statuses, owners,
                 posts=None, post_orders=None, single_dates=None, intervals=None,
                 times=None, busy_days=None, prices=None, channel_formats=None):
        self.source_project = source_project
        self.source_orders = source_orders
        self.channel_statuses = channel_statuses
        self.owners = owners
        self.posts = posts or {}
        self.post_orders = post_orders or {}
        self.single_dates = single_dates or {}
        self.intervals = intervals or {}
        self.times = times or {}
        self.busy_days = busy_days or {}
        self.prices = prices or {}
        self.channel_formats = channel_formats or {}

        self._status_by_channel = {
            order.channel_id: channel_statuses[order.id] for order in source_orders
        }

        self.created_projects = []
        self.created_project_idents = []
        self.created_orders = []
        self.created_order_idents = []
        self.created_posts = []
        self.post_idents = []
        self.post_comments = []
        self.post_texts = []
        self.post_buttons = []
        self.post_contents = []
        self.order_matches = []
        self.order_status = {}
        self.project_status = {}
        self.order_dates = []
        self.order_date_intervals = []
        self.time_intervals = []
        self.order_prices = []
        self.project_carts = {}

        self._new_order_channel = {}
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def get_project(self, project_id):
        return self.source_project if project_id == self.source_project.id else None

    async def get_project_orders_readonly(self, project_id):
        return deepcopy(self.source_orders)

    async def get_channel_status(self, channel_id):
        return self._status_by_channel.get(channel_id)

    async def get_channel_formats(self, channel_id):
        if channel_id in self.channel_formats:
            return self.channel_formats[channel_id]
        return [order.format for order in self.source_orders if order.channel_id == channel_id]

    async def get_order_executor_id(self, user_id, channel_id):
        return self.owners.get(channel_id, uuid4())

    async def create_project(self, project):
        self.created_projects.append(project)
        self.project_status[project.id] = project.status

    async def create_project_identifier(self, ident):
        self.created_project_idents.append(ident)

    async def create_order(self, order):
        self.created_orders.append(order)
        self.order_status[order.id] = order.status
        self._new_order_channel[order.id] = order.channel_id

    async def create_order_identifier(self, ident):
        self.created_order_idents.append(ident)

    async def get_project_post_id(self, project_id):
        return list(self.posts.keys())

    async def get_post_full(self, post_id):
        return deepcopy(self.posts.get(post_id))

    async def get_post_order_ids(self, post_id):
        return list(self.post_orders.get(post_id, []))

    async def create_post(self, id, project_id, match_type):
        self.created_posts.append({"id": id, "project_id": project_id, "match_type": match_type})

    async def create_post_identificator(self, post_id):
        self.post_idents.append(post_id)

    async def create_post_comment(self, id, post_id, comment):
        self.post_comments.append({"id": id, "post_id": post_id, "comment": comment})

    async def create_post_text(self, id, post_id, content, content_type):
        self.post_texts.append({"id": id, "post_id": post_id, "content": content})

    async def create_post_button(self, id, post_id, content, url, content_type):
        self.post_buttons.append({"id": id, "post_id": post_id, "content": content, "url": url})

    async def create_post_content(self, id, post_id, content, name, content_type):
        self.post_contents.append({"id": id, "post_id": post_id, "content": content, "name": name})

    async def create_order_match(self, match):
        self.order_matches.append(match)

    async def change_order_status(self, order_id, status):
        self.order_status[order_id] = status

    async def change_project_status(self, project_id, status):
        self.project_status[project_id] = status

    async def get_post_time_interval(self, order_id):
        return self.times.get(order_id)

    async def get_order_date(self, order_id):
        return self.single_dates.get(order_id)

    async def get_order_dates(self, order_id):
        return list(self.intervals.get(order_id, []))

    async def is_busy_calendar_day(self, order_id, day):
        channel_id = self._new_order_channel[order_id]
        return day in self.busy_days.get(channel_id, set())

    async def is_busy_calendar_days(self, order_id, days):
        channel_id = self._new_order_channel[order_id]
        busy = self.busy_days.get(channel_id, set())
        return len([d for d in days if d not in busy])

    async def create_order_date(self, order_date):
        self.order_dates.append(order_date)

    async def create_order_date_interval(self, date_interval):
        self.order_date_intervals.append(date_interval)

    async def create_time_interval(self, time_interval):
        self.time_intervals.append(time_interval)

    async def get_order_advertiser_prices(self, order_id):
        channel_id = self._new_order_channel[order_id]
        order = next(o for o in self.created_orders if o.id == order_id)
        if order.format not in await self.get_channel_formats(channel_id):
            return None
        price = self.prices.get(channel_id, 100000)
        return ChannelFormatPrices(
            channel_id=channel_id, format=order.format, blogger_price=price, advertiser_price=price,
        )

    async def setup_order_price(self, order_crushes):
        self.order_prices.extend(order_crushes)

    async def get_project_cart(self, project_id):
        return []

    async def record_project_cart(self, cart, user_id):
        self.project_carts[cart[0].project_id if cart else None] = cart

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def close(self):
        self.closed = True


def _interactor(gw, now=None):
    return CopyProjectInteractor(
        db_gateway=gw,
        project_service=ProjectService(),
        post_service=PostService(),
        wallet_service=WalletService(),
        project_cart_service=ProjectCartService(),
        now_provider=(lambda: now) if now is not None else (lambda: datetime(2026, 1, 1, 8, 0)),
    )


def _input(project, user_id=None):
    return CopyProjectInput(project_id=project.id, user_id=user_id or project.user_id)


def _order(project_id, channel_id, fmt=Format.telegram_1_24):
    return Order(
        id=uuid4(), project_id=project_id, executor_id=uuid4(), channel_id=channel_id,
        format=fmt, price=999.0, status=OrderStatus.saved, created=datetime.utcnow(),
        updated=datetime.utcnow(),
    )


def _ti(order_id, time_from=time(10), time_to=time(12)):
    return TimeInterval(id=uuid4(), order_id=order_id, time_from=time_from, time_to=time_to)


def _base_setup(*, statuses=None, single_dates=None, intervals=None, times=None,
                busy_days=None, posts=None, post_orders=None, prices=None):
    user_id = uuid4()
    project = Project(
        id=uuid4(), user_id=user_id, name="Source RK",
        status=ProjectStatus.saved, created=datetime.utcnow(), updated=datetime.utcnow(),
    )
    channel_id = uuid4()
    order = _order(project.id, channel_id)
    statuses = statuses or {order.id: ChannelStatus.active}
    gw = FakeGateway(
        source_project=project,
        source_orders=[order],
        channel_statuses=statuses,
        owners={channel_id: uuid4()},
        posts=posts or {},
        post_orders=post_orders or {},
        single_dates=single_dates or {},
        intervals=intervals or {},
        times=times or {},
        busy_days=busy_days or {},
        prices=prices or {},
    )
    return gw, project, order, channel_id


# --- Access control -----------------------------------------------------------

def test_foreign_project_raises_access_denied():
    gw, project, order, channel_id = _base_setup(
        single_dates={}, times={},
    )
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    with pytest.raises(AccessDenied):
        run(_interactor(gw)(_input(project, user_id=uuid4())))

    assert gw.created_projects == []
    assert gw.closed is True


# --- Source immutability & new identifiers -----------------------------------

def test_source_project_unchanged_and_new_project_id():
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    out = run(_interactor(gw)(_input(project)))

    assert out.project_id != project.id
    assert gw.source_project.name == "Source RK"
    assert gw.source_project.status == ProjectStatus.saved
    assert len(gw.created_project_idents) == 1
    assert gw.created_project_idents[0].project_id == out.project_id
    assert gw.project_status[out.project_id] == ProjectStatus.saved
    assert gw.committed is True


def test_orders_new_ids_point_to_new_project_keep_channel():
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    out = run(_interactor(gw)(_input(project)))

    created = gw.created_orders
    assert len(created) == 1
    assert created[0].id != order.id
    assert created[0].project_id == out.project_id
    assert created[0].channel_id == channel_id
    assert created[0].format == order.format
    assert len(gw.created_order_idents) == 1


def test_executor_recomputed_via_gateway():
    gw, project, order, channel_id = _base_setup()
    owner = uuid4()
    gw.owners = {channel_id: owner}
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    run(_interactor(gw)(_input(project)))

    assert gw.created_orders[0].executor_id == owner


def test_prices_recomputed_not_copied():
    gw, project, order, channel_id = _base_setup()
    gw.prices = {channel_id: 50000}
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    run(_interactor(gw)(_input(project)))

    new_order_id = gw.created_orders[0].id
    assert gw.created_orders[0].price is None
    blogger = [c for c in gw.order_prices if c.type == OrderCrushType.blogger_order_amount]
    assert blogger and blogger[0].amount == 50000
    assert all(c.order_id == new_order_id for c in gw.order_prices)
    assert gw.order_status[new_order_id] == OrderStatus.saved


# --- Posts / matches / comments ----------------------------------------------

def _post(project_id, *, comment="hi", match_type=PostMatchType.individual, files=None):
    return Post(
        id=uuid4(), match_type=match_type, project_id=project_id,
        comment=comment, files=files if files is not None else [
            File(content_type=ContentType.text, content="body", name=None),
        ],
    )


def test_posts_cloned_with_new_ids_and_relations():
    gw, project, order, channel_id = _base_setup()
    src_post = _post(project.id)
    gw.posts = {src_post.id: src_post}
    gw.post_orders = {src_post.id: [order.id]}
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    out = run(_interactor(gw)(_input(project)))

    assert len(gw.created_posts) == 1
    new_post_id = gw.created_posts[0]["id"]
    assert new_post_id != src_post.id
    assert gw.created_posts[0]["project_id"] == out.project_id
    new_order_id = gw.created_orders[0].id
    assert len(gw.order_matches) == 1
    assert gw.order_matches[0].order_id == new_order_id
    assert gw.order_matches[0].post_id == new_post_id
    assert gw.order_matches[0].project_id == out.project_id


def test_comment_copied_text_new_id():
    gw, project, order, channel_id = _base_setup()
    src_post = _post(project.id, comment="keep me")
    gw.posts = {src_post.id: src_post}
    gw.post_orders = {src_post.id: [order.id]}
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    run(_interactor(gw)(_input(project)))

    assert len(gw.post_comments) == 1
    assert gw.post_comments[0]["comment"] == "keep me"


def test_match_type_preserved_universal():
    gw, project, order, channel_id = _base_setup()
    src_post = _post(project.id, match_type=PostMatchType.universal)
    gw.posts = {src_post.id: src_post}
    gw.post_orders = {src_post.id: [order.id]}
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    run(_interactor(gw)(_input(project)))

    assert gw.created_posts[0]["match_type"] == PostMatchType.universal


def test_post_content_and_button_cloned():
    gw, project, order, channel_id = _base_setup()
    src_post = _post(project.id, files=[
        File(content_type=ContentType.text, content="tz-url", name=None),
        Button(content_type=ContentType.button, content="Buy", url="https://x"),
        File(content_type=ContentType.photo, content="s3://key", name="img.png"),
    ])
    gw.posts = {src_post.id: src_post}
    gw.post_orders = {src_post.id: [order.id]}
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    run(_interactor(gw)(_input(project)))

    assert gw.post_texts[0]["content"] == "tz-url"
    assert gw.post_buttons[0]["url"] == "https://x"
    assert gw.post_contents[0]["content"] == "s3://key"


def test_single_match_per_order_invariant():
    gw, project, order, channel_id = _base_setup()
    post_a = _post(project.id)
    post_b = _post(project.id)
    gw.posts = {post_a.id: post_a, post_b.id: post_b}
    gw.post_orders = {post_a.id: [order.id], post_b.id: [order.id]}
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    run(_interactor(gw)(_input(project)))

    new_order_id = gw.created_orders[0].id
    assert len([m for m in gw.order_matches if m.order_id == new_order_id]) == 1


# --- Time preserved -----------------------------------------------------------

def test_time_from_to_preserved():
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id, time_from=time(9, 30), time_to=time(11, 45))}

    run(_interactor(gw)(_input(project)))

    ti = gw.time_intervals[0]
    assert ti.time_from == time(9, 30)
    assert ti.time_to == time(11, 45)


# --- Single date resolution (A/B/C/D) -----------------------------------------

def test_past_source_date_moves_to_tomorrow():
    now = datetime(2026, 6, 10, 8, 0)
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 1, 1)}  # Case A: past
    gw.times = {order.id: _ti(order.id, time_from=time(20), time_to=time(22))}

    run(_interactor(gw, now=now)(_input(project)))

    assert gw.order_dates[0].date == date(2026, 6, 11)


def test_today_time_passed_moves_to_tomorrow():
    now = datetime(2026, 6, 10, 21, 0)
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 6, 10)}  # Case B
    gw.times = {order.id: _ti(order.id, time_from=time(20), time_to=time(22))}

    run(_interactor(gw, now=now)(_input(project)))

    assert gw.order_dates[0].date == date(2026, 6, 11)


def test_today_time_not_passed_stays_today():
    now = datetime(2026, 6, 10, 8, 0)
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 6, 10)}  # Case C
    gw.times = {order.id: _ti(order.id, time_from=time(20), time_to=time(22))}

    run(_interactor(gw, now=now)(_input(project)))

    assert gw.order_dates[0].date == date(2026, 6, 10)


def test_future_source_date_unchanged():
    now = datetime(2026, 6, 1, 8, 0)
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 6, 20)}  # Case D
    gw.times = {order.id: _ti(order.id, time_from=time(20), time_to=time(22))}

    run(_interactor(gw, now=now)(_input(project)))

    assert gw.order_dates[0].date == date(2026, 6, 20)


def test_busy_target_day_raises_and_rolls_back():
    now = datetime(2026, 6, 1, 8, 0)
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 6, 5)}  # future, unchanged -> 6/5
    gw.times = {order.id: _ti(order.id, time_from=time(20), time_to=time(22))}
    gw.busy_days = {channel_id: {date(2026, 6, 5)}}

    with pytest.raises(CalendarDayIsBusy):
        run(_interactor(gw, now=now)(_input(project)))

    assert gw.rolled_back is True
    assert gw.committed is False


# --- Interval resolution ------------------------------------------------------

def test_interval_future_unchanged_duration_preserved():
    now = datetime(2026, 6, 1, 8, 0)
    gw, project, order, channel_id = _base_setup()
    gw.intervals = {order.id: [DateInterval(
        id=uuid4(), order_id=order.id, date_from=date(2026, 6, 10), date_to=date(2026, 6, 12),
    )]}
    gw.times = {order.id: _ti(order.id, time_from=time(20), time_to=time(22))}

    run(_interactor(gw, now=now)(_input(project)))

    di = gw.order_date_intervals[0]
    assert di.date_from == date(2026, 6, 10)
    assert di.date_to == date(2026, 6, 12)


def test_interval_shifts_whole_range_when_start_moved():
    now = datetime(2026, 6, 10, 21, 0)  # today, time passed -> tomorrow
    gw, project, order, channel_id = _base_setup()
    gw.intervals = {order.id: [DateInterval(
        id=uuid4(), order_id=order.id, date_from=date(2026, 6, 10), date_to=date(2026, 6, 12),
    )]}
    gw.times = {order.id: _ti(order.id, time_from=time(20), time_to=time(22))}

    run(_interactor(gw, now=now)(_input(project)))

    di = gw.order_date_intervals[0]
    assert di.date_from == date(2026, 6, 11)  # 10->11
    assert di.date_to == date(2026, 6, 13)  # whole interval shifted by 1


def test_interval_past_shifts_to_tomorrow_keeps_duration():
    now = datetime(2026, 6, 10, 8, 0)
    gw, project, order, channel_id = _base_setup()
    gw.intervals = {order.id: [DateInterval(
        id=uuid4(), order_id=order.id, date_from=date(2026, 6, 1), date_to=date(2026, 6, 3),
    )]}
    gw.times = {order.id: _ti(order.id, time_from=time(20), time_to=time(22))}

    run(_interactor(gw, now=now)(_input(project)))

    di = gw.order_date_intervals[0]
    assert di.date_from == date(2026, 6, 11)
    assert (di.date_to - di.date_from).days == 2


def test_one_day_interval_preserved():
    now = datetime(2026, 6, 1, 8, 0)
    gw, project, order, channel_id = _base_setup()
    gw.intervals = {order.id: [DateInterval(
        id=uuid4(), order_id=order.id, date_from=date(2026, 6, 10), date_to=date(2026, 6, 10),
    )]}
    gw.times = {order.id: _ti(order.id, time_from=time(20), time_to=time(22))}

    run(_interactor(gw, now=now)(_input(project)))

    di = gw.order_date_intervals[0]
    assert di.date_from == di.date_to == date(2026, 6, 10)


def test_interval_all_days_busy_raises():
    now = datetime(2026, 6, 1, 8, 0)
    gw, project, order, channel_id = _base_setup()
    gw.intervals = {order.id: [DateInterval(
        id=uuid4(), order_id=order.id, date_from=date(2026, 6, 10), date_to=date(2026, 6, 12),
    )]}
    gw.times = {order.id: _ti(order.id, time_from=time(20), time_to=time(22))}
    gw.busy_days = {channel_id: {date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)}}

    with pytest.raises(CalendarDayIsBusy):
        run(_interactor(gw, now=now)(_input(project)))

    assert gw.rolled_back is True


# --- Multiple orders / different dates ----------------------------------------

def test_different_orders_get_independent_dates():
    now = datetime(2026, 6, 1, 8, 0)
    project = Project(
        id=uuid4(), user_id=uuid4(), name="RK", status=ProjectStatus.saved,
        created=datetime.utcnow(), updated=datetime.utcnow(),
    )
    ch_a, ch_b = uuid4(), uuid4()
    order_a = _order(project.id, ch_a)
    order_b = _order(project.id, ch_b)
    gw = FakeGateway(
        source_project=project, source_orders=[order_a, order_b],
        channel_statuses={order_a.id: ChannelStatus.active, order_b.id: ChannelStatus.active},
        owners={ch_a: uuid4(), ch_b: uuid4()},
        single_dates={order_a.id: date(2026, 6, 5), order_b.id: date(2026, 6, 20)},
        times={order_a.id: _ti(order_a.id, time_from=time(20), time_to=time(22)),
               order_b.id: _ti(order_b.id, time_from=time(20), time_to=time(22))},
    )

    run(_interactor(gw, now=now)(_input(project)))

    values = {pd.date for pd in gw.order_dates}
    assert values == {date(2026, 6, 5), date(2026, 6, 20)}


# --- Channel filtering --------------------------------------------------------

def test_inactive_banned_channels_excluded():
    now = datetime(2026, 6, 1, 8, 0)
    project = Project(
        id=uuid4(), user_id=uuid4(), name="RK", status=ProjectStatus.saved,
        created=datetime.utcnow(), updated=datetime.utcnow(),
    )
    ch_ok, ch_bad = uuid4(), uuid4()
    order_ok = _order(project.id, ch_ok)
    order_bad = _order(project.id, ch_bad)
    gw = FakeGateway(
        source_project=project, source_orders=[order_ok, order_bad],
        channel_statuses={order_ok.id: ChannelStatus.active, order_bad.id: ChannelStatus.banned},
        owners={ch_ok: uuid4(), ch_bad: uuid4()},
        single_dates={order_ok.id: date(2026, 6, 5), order_bad.id: date(2026, 6, 5)},
        times={order_ok.id: _ti(order_ok.id, time_from=time(20), time_to=time(22))},
    )

    run(_interactor(gw, now=now)(_input(project)))

    assert len(gw.created_orders) == 1
    assert gw.created_orders[0].channel_id == ch_ok


def test_all_channels_filtered_raises():
    project = Project(
        id=uuid4(), user_id=uuid4(), name="RK", status=ProjectStatus.saved,
        created=datetime.utcnow(), updated=datetime.utcnow(),
    )
    ch = uuid4()
    order = _order(project.id, ch)
    gw = FakeGateway(
        source_project=project, source_orders=[order],
        channel_statuses={order.id: ChannelStatus.inactive},
        owners={ch: uuid4()},
    )
    with pytest.raises(EmptyProjectCart):
        run(_interactor(gw)(_input(project)))
    assert gw.created_projects == []


def test_unavailable_format_copied_without_price():
    project = Project(
        id=uuid4(), user_id=uuid4(), name="RK", status=ProjectStatus.saved,
        created=datetime.utcnow(), updated=datetime.utcnow(),
    )
    ch_ok, ch_bad = uuid4(), uuid4()
    order_ok = _order(project.id, ch_ok)
    order_bad = _order(project.id, ch_bad, fmt=Format.telegram_1_24)
    gw = FakeGateway(
        source_project=project, source_orders=[order_ok, order_bad],
        channel_statuses={order_ok.id: ChannelStatus.active, order_bad.id: ChannelStatus.active},
        owners={ch_ok: uuid4(), ch_bad: uuid4()},
        single_dates={order_ok.id: date(2026, 1, 5), order_bad.id: date(2026, 1, 5)},
        times={order_ok.id: _ti(order_ok.id), order_bad.id: _ti(order_bad.id)},
        channel_formats={ch_bad: []},
    )

    run(_interactor(gw)(_input(project)))

    new_by_channel = {o.channel_id: o for o in gw.created_orders}
    assert set(new_by_channel) == {ch_ok, ch_bad}
    assert new_by_channel[ch_bad].format == Format.telegram_1_24
    priced_orders = {c.order_id for c in gw.order_prices}
    assert priced_orders == {new_by_channel[ch_ok].id}
    assert gw.order_status[new_by_channel[ch_bad].id] == OrderStatus.saved
    assert gw.committed is True


# --- Saved without dates ------------------------------------------------------

def test_missing_time_interval_raises_and_rolls_back():
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {}  # no time interval

    with pytest.raises(DateOrTimeNotSetup):
        run(_interactor(gw)(_input(project)))

    assert gw.rolled_back is True
    assert gw.committed is False


def test_missing_date_raises_and_rolls_back():
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {}
    gw.intervals = {}
    gw.times = {order.id: _ti(order.id)}

    with pytest.raises(DateOrTimeNotSetup):
        run(_interactor(gw)(_input(project)))

    assert gw.rolled_back is True
    assert gw.committed is False


# --- Repeat & rollback --------------------------------------------------------

def test_repeat_clone_independent():
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}
    interactor = _interactor(gw)

    out1 = run(interactor(_input(project)))
    out2 = run(interactor(_input(project)))

    assert out1.project_id != out2.project_id
    assert set(out1.order_ids).isdisjoint(out2.order_ids)


def test_failure_triggers_rollback_without_commit():
    gw, project, order, channel_id = _base_setup()
    gw.single_dates = {order.id: date(2026, 1, 5)}
    gw.times = {order.id: _ti(order.id)}

    async def boom(time_interval):
        raise RuntimeError("db down")

    gw.create_time_interval = boom

    with pytest.raises(RuntimeError):
        run(_interactor(gw)(_input(project)))

    assert gw.rolled_back is True
    assert gw.committed is False


# --- Pure date-resolver rules -------------------------------------------------

def test_resolve_clone_date_rules():
    today = date(2026, 6, 10)
    assert resolve_clone_date(date(2026, 1, 1), today, time(20), time(8)) == date(2026, 6, 11)  # A
    assert resolve_clone_date(today, today, time(20), time(21)) == date(2026, 6, 11)  # B
    assert resolve_clone_date(today, today, time(20), time(8)) == today  # C
    assert resolve_clone_date(date(2026, 6, 20), today, time(8), time(9)) == date(2026, 6, 20)  # D


def test_resolve_clone_interval_shift_and_duration():
    today = date(2026, 6, 10)
    start, end = resolve_clone_interval(date(2026, 6, 1), date(2026, 6, 3), today, time(20), time(8))
    assert start == date(2026, 6, 11)
    assert (end - start).days == 2  # duration preserved


def test_resolve_clone_interval_future_unchanged():
    today = date(2026, 6, 1)
    start, end = resolve_clone_interval(date(2026, 6, 10), date(2026, 6, 12), today, time(8), time(9))
    assert (start, end) == (date(2026, 6, 10), date(2026, 6, 12))
