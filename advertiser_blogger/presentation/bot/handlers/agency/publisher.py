from datetime import datetime
from uuid import UUID

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.markdown import hlink
from dishka import FromDishka

from advertiser_blogger.application.read.project_agency.dto import ProjectAgencyActiveDtoInput
from advertiser_blogger.application.read.project_agency.use_case import ReadProjectAgencyInteractor
from advertiser_blogger.application.read.read_orders_tariff_approval.dto import ReadOrdersTariffApprovalDtoInput
from advertiser_blogger.application.read.read_orders_tariff_approval.use_case import ReadOrderTariffApprovalInteractor
from advertiser_blogger.application.record.get_project_agency_completed_report.dto import \
    GetProjectAgencyCompletedReportDtoInput
from advertiser_blogger.application.record.get_project_agency_completed_report.use_case import \
    GetProjectAgencyCompletedReportInteractor
from advertiser_blogger.application.record.order_agency_cancel.dto import OrderAgencyCancelDtoInput
from advertiser_blogger.application.record.order_agency_cancel.use_case import OrderAgencyCancelInteractor
from advertiser_blogger.application.record.publish_post_agency_order.dto import PublishPostAgencyOrderDtoInput
from advertiser_blogger.application.record.publish_post_agency_order.use_case import PublishPostAgencyOrderInteractor
from advertiser_blogger.domain.read.constants import Language
from advertiser_blogger.domain.record.order.constants import ProjectStatus, DeeplinkType, OrderStatus
from advertiser_blogger.infrastructure.bot.bot import TelegramBotService
from advertiser_blogger.infrastructure.db.repositories.bot_repository import BotRepository
from advertiser_blogger.infrastructure.db.repositories.read import ReadRepository
from advertiser_blogger.presentation.bot.common.build_post_url import build_post_url
from advertiser_blogger.presentation.bot.common.rec_orders import record_orders
from advertiser_blogger.presentation.bot.content.content import Content
from advertiser_blogger.presentation.bot.filters.get_publisher import GetManagerIdByPublisherFilter
from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard
from advertiser_blogger.presentation.bot.models.publisher import PublisherProject
from advertiser_blogger.presentation.bot.states.publisher import PubState

PublisherRouter = Router(name="PublisherRouter")
PublisherRouter.message.filter(GetManagerIdByPublisherFilter())


@PublisherRouter.message(F.text.in_(["Активные проекты", "Отправить ссылку на пост"]))
async def get_projects_active(
        message: Message, inline: FromDishka[InlineKeyboard],
        interactor: FromDishka[ReadProjectAgencyInteractor], user_id: UUID,
        state: FSMContext,
):
    response = await interactor(
        data=ProjectAgencyActiveDtoInput(
            # frozen projects too: some of their orders may be unfrozen one by one
            user_id=user_id, page=1, elements_on_page=None, status=[ProjectStatus.in_progress, ProjectStatus.frozen],
        )
    )
    await message.answer(
        "Вот список ваших активных проектов:", reply_markup=inline.show_projects(
            projects=response.projects,
        )
    )
    await state.set_state(PubState.active_orders)


@PublisherRouter.message(F.text == "Завершенные проекты")
async def get_projects_completed(
        message: Message, inline: FromDishka[InlineKeyboard],
        interactor: FromDishka[ReadProjectAgencyInteractor], user_id: UUID,
        state: FSMContext,
):
    response = await interactor(
        data=ProjectAgencyActiveDtoInput(
            user_id=user_id, page=1, elements_on_page=None, status=[ProjectStatus.completed],
        )
    )
    await message.answer(
        "Вот список ваших завершенных проектов:", reply_markup=inline.show_projects(
            projects=response.projects,
        )
    )
    await state.set_state(PubState.completed_orders)


@PublisherRouter.callback_query(PubState.active_orders)
async def get_orders_active(
        message: CallbackQuery, interactor: FromDishka[ReadOrderTariffApprovalInteractor],
        read_repo: FromDishka[ReadRepository], bot: FromDishka[Bot], inline: FromDishka[InlineKeyboard],
        # report_interactor: FromDishka[GetProjectAgencyReqApproveReportInteractor],
        state: FSMContext,
) -> None:
    project_id = UUID(message.data)
    project_name = await read_repo.read_project_name(project_id=project_id)
    if project_name is None:
        await read_repo.close()
        await bot.send_message(chat_id=message.from_user.id, text="Проект не найден")
        return
    response = await interactor(
        data=ReadOrdersTariffApprovalDtoInput(
            project_id=project_id, language=Language.ru, page=1, elements_on_page=None,
        )
    )
    await record_orders(orders=response.orders, state=state)
    channels = ""
    for count, i in enumerate(response.orders, start=1):
        channels += f"{count}. {i.url}\n"
    await bot.edit_message_text(
        chat_id=message.from_user.id,
        text=f"<b>{project_name}</b>\nСписок каналов:\n\n{channels}",
        reply_markup=inline.show_orders(orders=response.orders),
        message_id=message.message.message_id,
    )
    # report = await report_interactor(data=GetProjectAgencyRequestApproveReportDtoInput(project_id=project_id))
    # await bot.send_message(
    #     chat_id=message.from_user.id,
    #     text=f"Excel отчёт можно скачать по ссылке👇\n\n{hlink(title='Скачать', url=report.url)}",
    # )
    await message.answer()
    await state.set_state(PubState.show_order)


@PublisherRouter.callback_query(PubState.completed_orders)
async def get_orders_completed(
        message: CallbackQuery, interactor: FromDishka[ReadOrderTariffApprovalInteractor],
        read_repo: FromDishka[ReadRepository], bot: FromDishka[Bot], inline: FromDishka[InlineKeyboard],
        report_interactor: FromDishka[GetProjectAgencyCompletedReportInteractor],
        state: FSMContext,
) -> None:
    project_id = UUID(message.data)
    project_name = await read_repo.read_project_name(project_id=project_id)
    if project_name is None:
        await read_repo.close()
        await bot.send_message(chat_id=message.from_user.id, text="Проект не найден")
        return
    response = await interactor(
        data=ReadOrdersTariffApprovalDtoInput(
            project_id=project_id, language=Language.ru, page=1, elements_on_page=None,
        )
    )
    await record_orders(orders=response.orders, state=state)
    channels = ""
    for count, i in enumerate(response.orders, start=1):
        channels += f"{count}. {i.url}\n"
    await bot.edit_message_text(
        chat_id=message.from_user.id,
        text=f"<b>{project_name}</b>\nСписок каналов:\n\n{channels}",
        reply_markup=inline.show_orders(orders=response.orders),
        message_id=message.message.message_id,
    )
    await message.answer()
    report = await report_interactor(data=GetProjectAgencyCompletedReportDtoInput(project_id=project_id))
    await bot.send_message(
        chat_id=message.from_user.id,
        text=f"Excel отчёт можно скачать по ссылке👇\n\n{hlink(title='Скачать', url=report.url)}",
    )
    await state.set_state(PubState.show_order)


@PublisherRouter.callback_query(PubState.show_order)
async def show_order(
        message: CallbackQuery, bot: FromDishka[Bot], content: FromDishka[Content],
        state: FSMContext, tg_bot_service: FromDishka[TelegramBotService],
        inline: FromDishka[InlineKeyboard],
):
    order_id = UUID(message.data)
    deeplink_post_url = await tg_bot_service.create_post_link(type=DeeplinkType.post, order_id=order_id)
    data = await state.get_data()
    project = PublisherProject.model_validate_json(data.get("publisher_project"))
    for i in project.orders:
        if i.id == order_id:
            order = i
            break
    else:
        await bot.edit_message_text(
            chat_id=message.from_user.id, text="Заказ не найден, обратитесь в поддержку",
            message_id=message.message.message_id,
        )
        return
    if order.status in [
        OrderStatus.completed, OrderStatus.canceled, OrderStatus.rejected, OrderStatus.await_invoice,
        OrderStatus.frozen,
    ]:
        is_active = False
    else:
        is_active = True
    await bot.edit_message_text(
        chat_id=message.from_user.id, text=content.show_order(order=order),
        message_id=message.message.message_id, reply_markup=inline.publisher_order(
            deeplink_post_url=deeplink_post_url, is_active=is_active, order_id=order_id,
            published_post=order.published_post,
        )
    )
    await message.answer()
    await state.set_state(PubState.pre_send_post_url)


@PublisherRouter.callback_query(PubState.pre_send_post_url, F.data.startswith("c_"))
async def cancel_order(
        message: CallbackQuery, bot: FromDishka[Bot], state: FSMContext,
        interactor: FromDishka[OrderAgencyCancelInteractor],
        bot_repo: FromDishka[BotRepository],
):
    order_id = UUID(message.data.split("_")[1])
    project = await bot_repo.get_publisher_project_id_and_code(
        order_id=order_id, telegram_id=message.from_user.id,
    )
    await interactor(
        data=OrderAgencyCancelDtoInput(project_id=project.project_id, order_id=order_id, code=project.code)
    )
    await bot.edit_message_text(
        chat_id=message.from_user.id, text="Заказ отменен ✅", message_id=message.message.message_id,
    )
    await message.answer()
    await state.clear()


@PublisherRouter.callback_query(PubState.pre_send_post_url, F.data.startswith("s_"))
async def pre_send_post_url(
        message: CallbackQuery, bot: FromDishka[Bot], state: FSMContext,
):
    order_id = message.data.split("_")[1]
    await state.update_data(order_id_to_publish_post=order_id)
    await bot.edit_message_text(
        chat_id=message.from_user.id, text="Отправьте ссылку на пост или сделайте форвард поста сюда",
        message_id=message.message.message_id,
    )
    await state.set_state(PubState.send_post_url)
    await message.answer()


@PublisherRouter.message(PubState.send_post_url)
async def send_post_url(
        message: Message, bot: FromDishka[Bot], state: FSMContext,
        interactor: FromDishka[PublishPostAgencyOrderInteractor],
        bot_repo: FromDishka[BotRepository],
):
    post_url = build_post_url(message=message)
    data = await state.get_data()
    order_id = data.get("order_id_to_publish_post")
    if order_id is None:
        await bot.send_message(
            chat_id=message.from_user.id, text="При отправке поста возникла ошибка, попробуйте заново"
        )
    order_id = UUID(order_id)
    project = await bot_repo.get_publisher_project_id_and_code(
        order_id=order_id, telegram_id=message.from_user.id,
    )
    await interactor(
        data=PublishPostAgencyOrderDtoInput(
            project_id=project.project_id, order_id=order_id, post_url=post_url, published=datetime.utcnow(),
            code=project.code,
        )
    )
    await bot.send_message(chat_id=message.from_user.id, text="Пост отправлен ✅")


# @PublisherRouter.message()
# async def ggg(message: Message):
#     print(message.forward_from_chat)
#     print(message.forward_from_message_id)
