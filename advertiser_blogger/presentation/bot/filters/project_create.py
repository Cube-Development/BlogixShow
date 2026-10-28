from typing import Optional

from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

MENU_NAVIGATION_TEXTS = frozenset({
    "Создать РК",
    "Активные проекты",
    "Завершенные проекты",
    "Отправить ссылку на пост",
    "🚀 Активные проекты",
    "☑️ Завершенные проекты",
    "📑 Скачать эксель отчет",
    "Отмена",
})

PROJECT_CREATE_CALLBACK_PREFIX = "pc_"


def is_project_create_state(current_state: str | None) -> bool:
    return bool(current_state and str(current_state).startswith("ProjectCreateState"))


def is_project_create_collecting_state(current_state: str | None) -> bool:
    if not is_project_create_state(current_state):
        return False
    return "choosing_publish_mode" not in str(current_state)


class IsProjectCreateCollectInput(Filter):
    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name

    async def __call__(self, message: Message, state: FSMContext) -> bool:
        current_state = await state.get_state()
        if not is_project_create_collecting_state(current_state):
            return False
        text = (message.text or message.caption or "").strip()
        if text.startswith("/"):
            return False
        if text in MENU_NAVIGATION_TEXTS:
            return False
        return True
