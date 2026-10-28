from aiogram.fsm.state import State, StatesGroup


class CollectCreateorderState(StatesGroup):
    awaiting_post = State()
    awaiting_accept = State()
