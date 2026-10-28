from aiogram import Router, Bot, types
from aiogram.filters.exception import ExceptionTypeFilter
from dishka import FromDishka
from aiogram.exceptions import TelegramBadRequest

from advertiser_blogger.application.common.exceptions.application_error import AttachTgUserNotFound, ManagerNotFound, \
    AccessDenied, PostAlreadyPublished, OrderNotAccepted, OrderNotFound
from advertiser_blogger.application.common.exceptions.bot_error import DeeplinkError

error_catcher = Router(name="ErrorCatcher")


@error_catcher.error(ExceptionTypeFilter(AttachTgUserNotFound))
async def catch_empty_current_basket(update: types.ErrorEvent, bot: FromDishka[Bot]):
    await bot.send_message(
        chat_id=update.update.message.from_user.id, text="Неверный диплинк(связь телеграм бот + сайт)"
    )


@error_catcher.error(ExceptionTypeFilter(ManagerNotFound))
async def catch_empty_current_basket(update: types.ErrorEvent, bot: FromDishka[Bot]):
    await bot.send_message(
        chat_id=update.update.message.from_user.id, text="Неверная ссылка, менеджер не найден"
    )


@error_catcher.error(ExceptionTypeFilter(DeeplinkError))
async def catch_empty_current_basket(update: types.ErrorEvent, bot: FromDishka[Bot]):
    await bot.send_message(
        chat_id=update.update.message.from_user.id, text="Неверная диплинк ссылка"
    )


@error_catcher.error(ExceptionTypeFilter(AccessDenied))
async def catch_empty_current_basket(update: types.ErrorEvent, bot: FromDishka[Bot]):
    await bot.send_message(
        chat_id=update.update.message.from_user.id, text="Нет доступа ⛔️"
    )


@error_catcher.error(ExceptionTypeFilter(PostAlreadyPublished))
async def catch_empty_current_basket(update: types.ErrorEvent, bot: FromDishka[Bot]):
    await bot.send_message(
        chat_id=update.update.message.from_user.id, text="Пост уже опубликован ⛔️"
    )


@error_catcher.error(ExceptionTypeFilter(OrderNotAccepted))
async def catch_empty_current_basket(update: types.ErrorEvent, bot: FromDishka[Bot]):
    await bot.send_message(
        chat_id=update.update.message.from_user.id, text="Заказ не принят ⛔️"
    )


@error_catcher.error(ExceptionTypeFilter(OrderNotFound))
async def catch_empty_current_basket(update: types.ErrorEvent, bot: FromDishka[Bot]):
    await bot.send_message(
        chat_id=update.update.message.from_user.id, text="Заказ не найден ⛔️"
    )


@error_catcher.error(ExceptionTypeFilter(TelegramBadRequest))
async def catch_empty_current_basket(update: types.ErrorEvent, bot: FromDishka[Bot]):
    print("TelegramBadRequest: ", update)
    # await bot.send_message(
    #     chat_id=update.update.message.from_user.id, text="Что-то пошло не так, попробуйте снова 🔄",
    # )
