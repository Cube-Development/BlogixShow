from datetime import date, datetime, time, timedelta
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.markdown import hlink
from dishka import FromDishka

from advertiser_blogger.application.common.exceptions.application_error import (
    DateNotFoundInTheInterval,
    OrderExpire,
)
from advertiser_blogger.application.interactors_bot.publish_post_broadcast.dto import (
    PublishObject,
    PublishPostBroadcastDtoInput,
    PublishPostFailureReason,
)
from advertiser_blogger.application.interactors_bot.publish_post_broadcast.use_case import (
    PublishPostBroadcastInteractor,
)
from advertiser_blogger.application.interactors_bot.read_orders_blogger.dto import (
    ReadOrdersBloggerDtoInput,
)
from advertiser_blogger.application.interactors_bot.read_orders_blogger.use_case import (
    ReadOrdersBloggerInteractor,
)
from advertiser_blogger.application.read.read_blogger_projects.use_case import (
    ReadBloggerProjectsInteractor,
)
from advertiser_blogger.application.read.read_posts.dto import ReadProjectPostsDtoInput
from advertiser_blogger.application.read.read_posts.use_case import ReadPostsInteractor
from advertiser_blogger.application.record.get_blogger_report.dto import (
    BloggerReportDtoInput,
)
from advertiser_blogger.application.record.get_blogger_report.use_case import (
    BloggerReportInteractor,
)
from advertiser_blogger.domain.read.common.entities.date_time import DatePeriod
from advertiser_blogger.domain.record.order.constants import OrderStatus
from advertiser_blogger.domain.record.user.entities import User
from advertiser_blogger.infrastructure.bot.post_builder import (
    FileViewWithUrl,
    PostBuilder,
    PostBuildError,
    PostResponse,
)
from advertiser_blogger.infrastructure.db.repositories.record import UserRepository
from advertiser_blogger.infrastructure.parsers.telegram_public_channel_album_ids import (
    TelegramPublicChannelAlbumIdsProvider,
)
from advertiser_blogger.presentation.bot.common.active_projects import (
    get_selected_date,
    send_active_projects_list,
    set_selected_date,
    tashkent_today,
)
from advertiser_blogger.presentation.bot.common.messages import PUBLISH_FAILURE_MESSAGES
from advertiser_blogger.presentation.bot.common.parse_broadcast_posts import (
    parse_broadcast_posts,
)
from advertiser_blogger.presentation.bot.filters.get_user import GetUserByTelegramId
from advertiser_blogger.presentation.bot.handlers.user.user import send_post
from advertiser_blogger.presentation.bot.keyboards.inline import (
    BP_CAL_BACK,
    BP_CAL_DAY_PREFIX,
    BP_CAL_IGNORE,
    BP_CAL_NAV_PREFIX,
    BP_DAY_PICK,
    BP_DAY_TODAY,
    BP_DAY_TOMORROW,
    BP_PROJ_PREFIX,
    InlineKeyboard,
)
from advertiser_blogger.presentation.bot.models.blogger import (
    BloggerPublishData,
    BloggerPublishDataSet,
    PublishOrderData,
)
from advertiser_blogger.presentation.bot.states.blogger import BloggerState
from configuration.common import CommonConfig


BloggerRouter = Router(name="BloggerRouter")
BloggerRouter.message.filter(GetUserByTelegramId())
BloggerRouter.callback_query.filter(GetUserByTelegramId())


@BloggerRouter.message(F.text == "📑 Скачать эксель отчет")
async def get_excel_report(
    message: Message,
    bot: FromDishka[Bot],
    interactor: FromDishka[BloggerReportInteractor],
    user: User,
):
    now = datetime.utcnow() + timedelta(hours=5)
    on_week_ago = now - timedelta(days=7)
    response = await interactor(
        data=BloggerReportDtoInput(
            user_id=user.id,
            date_period=DatePeriod(date_from=on_week_ago.date(), date_to=now.date()),
            telegram_id=message.from_user.id,
        )
    )
    await bot.send_message(
        chat_id=message.from_user.id,
        text=f"Отчет можно скачать по ссылке:\n\n {hlink(title=response.file_name, url=response.url)}",
    )


@BloggerRouter.message(
    F.text.in_(
        [
            "🚀 Активные проекты",
            # "☑️ Завершенные проекты",
        ]
    )
)
async def get_projects_active(
    message: Message,
    inline: FromDishka[InlineKeyboard],
    interactor: FromDishka[ReadBloggerProjectsInteractor],
    user: User,
    state: FSMContext,
):
    await set_selected_date(state, tashkent_today())
    await send_active_projects_list(
        message=message,
        user=user,
        inline=inline,
        interactor=interactor,
        state=state,
    )


@BloggerRouter.callback_query(F.data == BP_DAY_TODAY)
async def active_projects_tab_today(
    callback: CallbackQuery,
    inline: FromDishka[InlineKeyboard],
    interactor: FromDishka[ReadBloggerProjectsInteractor],
    user: User,
    state: FSMContext,
):
    await set_selected_date(state, tashkent_today())
    await callback.answer()
    await send_active_projects_list(
        message=callback.message,
        user=user,
        inline=inline,
        interactor=interactor,
        state=state,
        edit=True,
    )


@BloggerRouter.callback_query(F.data == BP_DAY_TOMORROW)
async def active_projects_tab_tomorrow(
    callback: CallbackQuery,
    inline: FromDishka[InlineKeyboard],
    interactor: FromDishka[ReadBloggerProjectsInteractor],
    user: User,
    state: FSMContext,
):
    await set_selected_date(state, tashkent_today() + timedelta(days=1))
    await callback.answer()
    await send_active_projects_list(
        message=callback.message,
        user=user,
        inline=inline,
        interactor=interactor,
        state=state,
        edit=True,
    )


@BloggerRouter.callback_query(F.data == BP_DAY_PICK)
async def active_projects_tab_pick_date(
    callback: CallbackQuery,
    inline: FromDishka[InlineKeyboard],
    state: FSMContext,
):
    on_date = await get_selected_date(state)
    await callback.answer()
    try:
        await callback.message.edit_text(
            text="Выберите дату:",
            reply_markup=inline.blogger_date_calendar(
                year=on_date.year, month=on_date.month
            ),
        )
    except TelegramBadRequest:
        await callback.message.answer(
            text="Выберите дату:",
            reply_markup=inline.blogger_date_calendar(
                year=on_date.year, month=on_date.month
            ),
        )


@BloggerRouter.callback_query(F.data == BP_CAL_IGNORE)
async def active_projects_calendar_ignore(callback: CallbackQuery):
    await callback.answer()


@BloggerRouter.callback_query(F.data == BP_CAL_BACK)
async def active_projects_calendar_back(
    callback: CallbackQuery,
    inline: FromDishka[InlineKeyboard],
    interactor: FromDishka[ReadBloggerProjectsInteractor],
    user: User,
    state: FSMContext,
):
    await callback.answer()
    await send_active_projects_list(
        message=callback.message,
        user=user,
        inline=inline,
        interactor=interactor,
        state=state,
        edit=True,
    )


@BloggerRouter.callback_query(F.data.startswith(BP_CAL_NAV_PREFIX))
async def active_projects_calendar_nav(
    callback: CallbackQuery,
    inline: FromDishka[InlineKeyboard],
):
    raw = callback.data.removeprefix(BP_CAL_NAV_PREFIX)
    try:
        year_str, month_str = raw.split("-", maxsplit=1)
        year, month = int(year_str), int(month_str)
        date(year, month, 1)
    except (ValueError, TypeError):
        await callback.answer()
        return
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(
            reply_markup=inline.blogger_date_calendar(year=year, month=month),
        )
    except TelegramBadRequest:
        pass


@BloggerRouter.callback_query(F.data.startswith(BP_CAL_DAY_PREFIX))
async def active_projects_calendar_day(
    callback: CallbackQuery,
    inline: FromDishka[InlineKeyboard],
    interactor: FromDishka[ReadBloggerProjectsInteractor],
    user: User,
    state: FSMContext,
):
    raw = callback.data.removeprefix(BP_CAL_DAY_PREFIX)
    try:
        on_date = date.fromisoformat(raw)
    except ValueError:
        await callback.answer()
        return
    await set_selected_date(state, on_date)
    await callback.answer()
    await send_active_projects_list(
        message=callback.message,
        user=user,
        inline=inline,
        interactor=interactor,
        state=state,
        edit=True,
    )


@BloggerRouter.callback_query(F.data.startswith(BP_PROJ_PREFIX))
async def start_send_published_post_url(
    message: CallbackQuery,
    bot: FromDishka[Bot],
    user: User,
    repo: FromDishka[UserRepository],
    interactor: FromDishka[ReadOrdersBloggerInteractor],
    state: FSMContext,
    album_ids_provider: FromDishka[TelegramPublicChannelAlbumIdsProvider],
    config: FromDishka[CommonConfig],
) -> None:
    raw_project_id = message.data.removeprefix(BP_PROJ_PREFIX)
    try:
        project_id = UUID(raw_project_id)
    except ValueError:
        await message.answer()
        return
    on_date = await get_selected_date(state)
    response = await interactor(
        data=ReadOrdersBloggerDtoInput(
            user_id=user.id,
            project_id=project_id,
            page=1,
            elements_on_page=None,
            only_in_progress=True,
            on_date=on_date,
        )
    )
    await message.answer()
    if response.completed is True:
        await bot.send_message(
            chat_id=message.from_user.id, text="✅ Все заказы в проекте выполнены"
        )
        return
    elif response.completed is False and len(response.posts) == 0:
        await bot.send_message(
            chat_id=message.from_user.id,
            text=f"😴 На {on_date.strftime('%d.%m.%Y')} постов нет",
        )
        return
    posts = BloggerPublishDataSet(project_id=project_id, posts=[])
    for post in response.posts:
        post_builder = PostBuilder(
            post=PostResponse(
                id=post.id,
                platform=post.platform,
                post_type=post.post_type,
                comment=post.comment,
                files=[
                    FileViewWithUrl(
                        content_type=i.content_type,
                        content=i.content,
                        name=i.name,
                        url=i.url,
                    )
                    for i in post.files
                ],
            )
        )
        try:
            post_object = post_builder.execute()
        except PostBuildError:
            await bot.send_message(
                chat_id=message.from_user.id, text="Ошибка в формировании поста ⛔️"
            )
            return
        post_message = await send_post(
            post=post_object,
            message=message,
            bot=bot,
            repo=repo,
            post_id=post.id,
            album_ids_provider=album_ids_provider,
            tz_channel_id=config.bot_project.tz_channel_id,
        )
        text = "Список каналов:\n"
        orders_to_publish = BloggerPublishData(message_id=0, post_id=post.id, orders=[])
        for count, order in enumerate(post.orders, start=1):
            orders_to_publish.orders.append(
                PublishOrderData(id=count, order_id=order.order_id)
            )
            if isinstance(order.publish_date, DatePeriod):
                publish_date = (
                    f"{datetime.strftime(order.publish_date.date_from, '%d.%m.%Y')} - "
                    f"{datetime.strftime(order.publish_date.date_to, '%d.%m.%Y')}"
                )
            elif isinstance(order.publish_date, date):
                publish_date = f"{datetime.strftime(order.publish_date, '%d.%m.%Y')}"
            else:
                publish_date = ""
            publish_time = (
                f"{time.strftime(order.publish_time.time_from, '%H:%M')} - "
                f"{time.strftime(order.publish_time.time_to, '%H:%M')}"
            )
            if order.status in [OrderStatus.canceled, OrderStatus.rejected]:
                status = "❌"
            elif order.status in [
                OrderStatus.post_review,
                OrderStatus.completed,
                OrderStatus.await_invoice,
            ]:
                status = "✅"
            elif order.status == OrderStatus.frozen:
                status = "❄️"
            else:
                status = ""
            text += f"{count}. {status}{order.url} | {publish_date} | {publish_time}\n"
        posts.posts.append(orders_to_publish)
        msg = await bot.send_message(
            chat_id=message.from_user.id, reply_to_message_id=post_message, text=text
        )
        orders_to_publish.message_id = msg.message_id
        await state.set_state(BloggerState.publish)
    await state.update_data(publish_posts=posts.model_dump_json())


@BloggerRouter.message(BloggerState.publish, F.reply_to_message)
async def publish_posts(
    message: Message,
    bot: FromDishka[Bot],
    state: FSMContext,
    publish_broadcast: FromDishka[PublishPostBroadcastInteractor],
    read_posts: FromDishka[ReadOrdersBloggerInteractor],
    user: User,
):
    data = await state.get_data()
    publish_posts = data.get("publish_posts")
    get_posts = BloggerPublishDataSet.model_validate_json(publish_posts)
    posts_from_message = parse_broadcast_posts(text=message.text)
    if len(posts_from_message) == 0:
        await bot.send_message(
            chat_id=message.from_user.id,
            text="Ошибка в построении ссылок, проверьте синтаксис ⛔️",
        )
        return
    post_broadcast = []
    orders_to_publish = None
    for i in get_posts.posts:
        if i.message_id == message.reply_to_message.message_id:
            orders_to_publish = i
            break
    if orders_to_publish is None:
        await bot.send_message(
            chat_id=message.from_user.id,
            text="Неверно сделан реплай на сообщение с заказами ⛔️",
        )
        return
    for i in orders_to_publish.orders:
        for j in posts_from_message:
            if i.id == j.id:
                post_broadcast.append(
                    PublishObject(order_id=i.order_id, post_url=j.post_url)
                )
    publish_result = await publish_broadcast(
        data=PublishPostBroadcastDtoInput(
            user_id=user.id,
            posts=post_broadcast,
            telegram_id=message.from_user.id,
        ),
    )
    result_by_order = {r.order_id: r for r in publish_result.results}
    order_id_to_display_id = {o.order_id: o.id for o in orders_to_publish.orders}
    response = await read_posts(
        data=ReadOrdersBloggerDtoInput(
            user_id=user.id,
            project_id=get_posts.project_id,
            page=1,
            elements_on_page=None,
        )
    )
    order_details = {}
    for post in response.posts:
        if post.id == orders_to_publish.post_id:
            for order in post.orders:
                order_details[order.order_id] = order
    text = "Список каналов:\n"
    published_count = 0
    for po in sorted(post_broadcast, key=lambda p: order_id_to_display_id[p.order_id]):
        order = order_details.get(po.order_id)
        if order is None:
            continue
        count = order_id_to_display_id[po.order_id]
        if isinstance(order.publish_date, DatePeriod):
            publish_date = (
                f"{datetime.strftime(order.publish_date.date_from, '%d.%m.%Y')} - "
                f"{datetime.strftime(order.publish_date.date_to, '%d.%m.%Y')}"
            )
        elif isinstance(order.publish_date, date):
            publish_date = f"{datetime.strftime(order.publish_date, '%d.%m.%Y')}"
        else:
            publish_date = ""
        publish_time = (
            f"{time.strftime(order.publish_time.time_from, '%H:%M')} - "
            f"{time.strftime(order.publish_time.time_to, '%H:%M')}"
        )
        result = result_by_order.get(po.order_id)
        if result is not None and result.success:
            published_count += 1
            text += f"{count}. ✅{order.url} | {publish_date} | {publish_time}\n"
        elif result is not None:
            reason_text = PUBLISH_FAILURE_MESSAGES.get(
                result.reason, "Не удалось разместить пост"
            )
            text += f"{count}. ⛔{order.url} | {publish_date} | {publish_time}\n   {reason_text}\n"
    text += f"\nРазмещено: {published_count} из {len(post_broadcast)}"
    await bot.send_message(
        chat_id=message.from_user.id,
        reply_to_message_id=message.reply_to_message.message_id,
        text=text,
    )
    await state.set_state(None)
