from aiogram.fsm.state import StatesGroup, State


class BloggerState(StatesGroup):
    publish = State()
