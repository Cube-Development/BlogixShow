from dataclasses import dataclass

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from advertiser_blogger.domain.record.user.entities import User


@dataclass(frozen=True)
class VerifyContext:
    user: User
    telegram_id: int
    chat_id: int
    message: Message | None = None
    state: FSMContext | None = None
