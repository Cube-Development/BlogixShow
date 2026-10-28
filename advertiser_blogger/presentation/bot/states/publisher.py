from aiogram.fsm.state import StatesGroup, State


class PubState(StatesGroup):
    active_orders = State()
    completed_orders = State()
    show_order = State()
    pre_send_post_url = State()
    send_post_url = State()
