from aiogram.fsm.state import StatesGroup, State


class ProjectCreateState(StatesGroup):
    choosing_publish_mode = State()
    awaiting_post = State()
    awaiting_channels_reply = State()
    preview = State()
    channel_menu = State()
    awaiting_replace = State()
    awaiting_replace_post = State()
    awaiting_edit_schedule = State()
    awaiting_edit_comment = State()
    confirming = State()
