from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from dishka import FromDishka
from advertiser_blogger.application.read.orders_observe.use_case import OrdersObserveInteractor
from advertiser_blogger.application.read.orders_observe_review.use_case import OrdersObserveReviewInteractor
from advertiser_blogger.application.record.retry_screenshot.dto import RetryScreenshotDtoInput
from advertiser_blogger.application.record.retry_screenshot.use_case import RetryScreenshotInteractor
from advertiser_blogger.infrastructure.bot.bot import TelegramBotService
from advertiser_blogger.presentation.bot.filters.self_connect_group import IsSelfConnectGroup, IsScreenshotTopic
from configuration.common import CommonConfig
from advertiser_blogger.application.read.orders_observe_review.parse_order_id import parse_order_id_from_screenshot


GroupSelfEmployedRouter = Router(name="GroupSelfEmployedRouter")


@GroupSelfEmployedRouter.message(Command(commands="orders"), IsSelfConnectGroup())
async def receive_message(
    message: Message, interactor: FromDishka[OrdersObserveInteractor],
    bot: FromDishka[TelegramBotService], config: FromDishka[CommonConfig]
) -> None:
    response = await interactor(data=None)
    chat = await bot.bot.get_chat(chat_id=config.bot.self_connect_group_chat_id)
    message = await bot.send_message(chat_id=config.bot.self_connect_group_chat_id, text=interactor.text(data=response))
    if chat.pinned_message is not None:
        await bot.unpin_message(chat_id=config.bot.self_connect_group_chat_id, message_id=chat.pinned_message.message_id)
        await bot.delete_message(chat_id=config.bot.self_connect_group_chat_id, message_id=chat.pinned_message.message_id)
    await bot.pin_message(chat_id=config.bot.self_connect_group_chat_id, message_id=message.message_id)



@GroupSelfEmployedRouter.message(Command(commands="retry"), IsScreenshotTopic())
async def retry_screenshot(
    message: Message, interactor: FromDishka[RetryScreenshotInteractor],
) -> None:
    replied = message.reply_to_message
    order_id = None
    if replied is not None:
        order_id = parse_order_id_from_screenshot(value=replied.caption or replied.text)
    if order_id is None:
        await message.reply(text="Ответьте командой /retry на сообщение со скриншотом заказа")
        return
    response = await interactor(data=RetryScreenshotDtoInput(order_id=order_id))
    if not response.event_found:
        await message.reply(text=f"Событие скриншота для заказа <code>{order_id}</code> не найдено")
        return
    await message.reply(text=f"Скриншот для заказа <code>{order_id}</code> поставлен на повторное создание")


# @GroupSelfEmployedRouter.message(
#         IsScreenshotTopic()
#         )
# async def catch_screenshots(
#     message: Message, interactor: FromDishka[OrdersObserveReviewInteractor],
#     bot: FromDishka[TelegramBotService], config: FromDishka[CommonConfig],
# ):
#     order_id = parse_order_id_from_screenshot(value=message.html_text)
#     if order_id is None:
#         return
#     print(f"catch_screenshots: parsed order_id={order_id}")
#     response = await interactor(data=order_id)
#     orders = [i for i in response.orders]
#     order_ids = [order.id for order in orders]
#     if order_id in order_ids:
#         await bot.bot.forward_message(
#             from_chat_id=message.chat.id,
#             chat_id=config.bot.self_connect_group_chat_id,
#             message_id=message.message_id,
#         )
#     else:
#         return