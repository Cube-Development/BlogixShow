from typing import Optional
import re

from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from advertiser_blogger.presentation.bot.common.forward_message import (
    TELEGRAM_URL_RE,
    get_message_body,
    is_any_forward,
)
from advertiser_blogger.presentation.bot.filters.collect_createorder import is_collect_createorder_state
from advertiser_blogger.presentation.bot.states.blogger import BloggerState

def is_telegram_link(text: str) -> bool:
    pattern = re.compile(r"https://(?:t|telegram)\.me/\S+")
    return pattern.fullmatch(text) is not None


class IsPostSubmission(Filter):
    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name

    async def __call__(self, message: Message, state: FSMContext) -> bool:
        if message.chat.type != "private":
            return False
        current_state = await state.get_state()
        if current_state and str(current_state).startswith("ProjectCreateState"):
            return False
        if is_collect_createorder_state(current_state):
            return False
        if is_any_forward(message=message):
            return True
        if current_state == BloggerState.publish and message.reply_to_message is not None:
            return False
        elif current_state == BloggerState.publish and message.reply_to_message is None:
            return is_telegram_link(text=message.text)
        body = get_message_body(message=message) or ""
        return bool(TELEGRAM_URL_RE.search(body))
