from datetime import date, datetime, timedelta

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from advertiser_blogger.application.common.constants import Timezone
from advertiser_blogger.application.read.read_blogger_projects.dto import (
    ReadBloggerProjectsDtoInput,
)
from advertiser_blogger.application.read.read_blogger_projects.use_case import (
    ReadBloggerProjectsInteractor,
)
from advertiser_blogger.domain.record.order.constants import ProjectStatus
from advertiser_blogger.domain.record.user.entities import User
from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard

ACTIVE_PROJECTS_LIST_MESSAGE = "Вот список ваших активных проектов:"
SELECTED_DATE_KEY = "selected_date"


def tashkent_today() -> date:
    return (datetime.utcnow() + timedelta(hours=Timezone.TASHKENT)).date()


async def get_selected_date(state: FSMContext) -> date:
    data = await state.get_data()
    raw = data.get(SELECTED_DATE_KEY)
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return tashkent_today()


async def set_selected_date(state: FSMContext, on_date: date) -> None:
    await state.update_data(**{SELECTED_DATE_KEY: on_date.isoformat()})


async def send_active_projects_list(
    message: Message,
    user: User,
    inline: InlineKeyboard,
    interactor: ReadBloggerProjectsInteractor,
    state: FSMContext,
    *,
    edit: bool = False,
) -> None:
    on_date = await get_selected_date(state)
    await set_selected_date(state, on_date)
    today = tashkent_today()
    response = await interactor(
        data=ReadBloggerProjectsDtoInput(
            user_id=user.id,
            page=1,
            elements_on_page=None,
            # a frozen project can still have orders unfrozen one by one, frozen orders themselves are hidden
            status=[ProjectStatus.in_progress, ProjectStatus.frozen],
            on_date=on_date,
        ),
    )
    reply_markup = inline.show_blogger_projects(
        projects=response.projects,
        selected_date=on_date,
        today=today,
    )
    if edit:
        try:
            await message.edit_text(
                text=ACTIVE_PROJECTS_LIST_MESSAGE,
                reply_markup=reply_markup,
            )
        except TelegramBadRequest:
            await message.answer(
                text=ACTIVE_PROJECTS_LIST_MESSAGE,
                reply_markup=reply_markup,
            )
    else:
        await message.answer(
            text=ACTIVE_PROJECTS_LIST_MESSAGE,
            reply_markup=reply_markup,
        )
