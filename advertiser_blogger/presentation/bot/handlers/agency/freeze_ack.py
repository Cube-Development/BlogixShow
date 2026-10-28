from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from dishka import FromDishka

from advertiser_blogger.application.common.exceptions.application_error import AccessDenied, OrderNotFound
from advertiser_blogger.application.record.acknowledge_order_freeze.dto import (
    AcknowledgeOrderFreezeDtoInput,
    FreezeAckResult,
)
from advertiser_blogger.application.record.acknowledge_order_freeze.use_case import (
    AcknowledgeOrderFreezeInteractor,
)
from advertiser_blogger.domain.record.user.entities import User
from advertiser_blogger.infrastructure.notification import freeze_texts
from advertiser_blogger.presentation.bot.filters.get_user import GetUserByTelegramId

# registered first: state handlers of other routers take any callback while the user is in their state
FreezeAckRouter = Router(name="FreezeAckRouter")
FreezeAckRouter.callback_query.filter(GetUserByTelegramId())


@FreezeAckRouter.callback_query(F.data.startswith(freeze_texts.FREEZE_ACK_PREFIX))
async def acknowledge_order_freeze(
    callback: CallbackQuery,
    interactor: FromDishka[AcknowledgeOrderFreezeInteractor],
    user: User,
):
    parsed = freeze_texts.parse_freeze_ack_callback(callback.data)
    if parsed is None:
        await callback.answer()
        return
    freeze_id, frozen = parsed
    try:
        response = await interactor(
            data=AcknowledgeOrderFreezeDtoInput(user_id=user.id, freeze_id=freeze_id, frozen=frozen),
        )
    except (OrderNotFound, AccessDenied):
        await callback.answer()
        return
    if response.result == FreezeAckResult.outdated:
        await callback.answer(text=freeze_texts.ACK_OUTDATED[user.language], show_alert=True)
    else:
        await callback.answer()
    try:
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=freeze_texts.ACK_DONE_BUTTON[user.language], callback_data=freeze_texts.FREEZE_ACK_DONE,
                ),
            ]]),
        )
    except TelegramBadRequest:
        # the markup is already the "done" one
        pass


@FreezeAckRouter.callback_query(F.data == freeze_texts.FREEZE_ACK_DONE)
async def acknowledge_order_freeze_done(callback: CallbackQuery):
    await callback.answer()
