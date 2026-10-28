from __future__ import annotations

from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from advertiser_blogger.presentation.bot.states.collect_createorder import CollectCreateorderState

_ACCEPT_CALLBACKS = frozenset({"cco_accept", "cco_replace"})
_COLLECT_CALLBACKS = frozenset({*_ACCEPT_CALLBACKS, "cco_cancel"})
_ACTIVE_COLLECT_STATES = frozenset({
    CollectCreateorderState.awaiting_post.state,
    CollectCreateorderState.awaiting_accept.state,
})


class IsCollectCreateorderStaleCallback(Filter):
    async def __call__(self, callback: CallbackQuery, state: FSMContext) -> bool:
        if callback.data not in _COLLECT_CALLBACKS:
            return False
        current = await state.get_state()
        if callback.data == "cco_cancel":
            return current not in _ACTIVE_COLLECT_STATES
        return current != CollectCreateorderState.awaiting_accept.state
