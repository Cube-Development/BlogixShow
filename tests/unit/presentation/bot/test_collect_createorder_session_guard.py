from __future__ import annotations

import asyncio
from uuid import uuid4

from advertiser_blogger.presentation.bot.common.collect_createorder_draft import (
    COLLECT_POST_KEY,
    COLLECT_PROJECT_ID_KEY,
    COLLECT_SESSION_ID_KEY,
    clear_collect_fsm_if_session_matches,
    start_new_collect_session,
)
from advertiser_blogger.presentation.bot.states.collect_createorder import CollectCreateorderState


class _FakeFsmContext:
    def __init__(self) -> None:
        self._data: dict = {}
        self._state: str | None = None

    async def get_data(self) -> dict:
        return dict(self._data)

    async def update_data(self, data: dict) -> None:
        self._data.update(data)

    async def set_state(self, state) -> None:
        self._state = state.state if hasattr(state, "state") else state

    async def get_state(self) -> str | None:
        return self._state

    async def clear(self) -> None:
        self._data = {}
        self._state = None


def _simulate_restart_after_start(state: _FakeFsmContext, old_session_id: str) -> str:
    async def _run() -> str:
        new_project_id = uuid4()
        await state.clear()
        new_session_id = await start_new_collect_session(
            state,
            project_id=new_project_id,
            order_id=None,
        )
        await state.set_state(CollectCreateorderState.awaiting_post)
        assert new_session_id != old_session_id
        return new_session_id

    return asyncio.run(_run())


def test_scenario_a_accept_success_does_not_clear_new_start_session() -> None:
    state = _FakeFsmContext()
    old_session_id = asyncio.run(
        start_new_collect_session(state, project_id=uuid4(), order_id=None),
    )
    awaiting_accept = CollectCreateorderState.awaiting_accept.state
    asyncio.run(state.set_state(CollectCreateorderState.awaiting_accept))

    new_session_id = _simulate_restart_after_start(state, old_session_id)

    cleared = asyncio.run(clear_collect_fsm_if_session_matches(state, old_session_id))
    assert cleared is False
    assert asyncio.run(state.get_state()) == CollectCreateorderState.awaiting_post.state
    assert (asyncio.run(state.get_data())).get(COLLECT_SESSION_ID_KEY) == new_session_id


def test_scenario_b_accept_exception_path_does_not_clear_new_start_session() -> None:
    state = _FakeFsmContext()
    old_session_id = asyncio.run(
        start_new_collect_session(state, project_id=uuid4(), order_id=None),
    )
    asyncio.run(state.set_state(CollectCreateorderState.awaiting_accept))

    new_session_id = _simulate_restart_after_start(state, old_session_id)

    cleared = asyncio.run(clear_collect_fsm_if_session_matches(state, old_session_id))
    assert cleared is False
    data = asyncio.run(state.get_data())
    assert data.get(COLLECT_SESSION_ID_KEY) == new_session_id
    assert asyncio.run(state.get_state()) == CollectCreateorderState.awaiting_post.state


def test_scenario_c_new_post_survives_old_accept_cleanup() -> None:
    state = _FakeFsmContext()
    old_session_id = asyncio.run(
        start_new_collect_session(state, project_id=uuid4(), order_id=None),
    )
    asyncio.run(state.set_state(CollectCreateorderState.awaiting_accept))

    new_session_id = _simulate_restart_after_start(state, old_session_id)

    async def _add_new_post_draft() -> None:
        await state.update_data({
            COLLECT_POST_KEY: {
                "local_id": "new-draft",
                "text": "new creative",
                "source_message_ids": [99],
                "bot_message_ids": [],
                "media_group_id": None,
                "kind": "text",
                "media": [],
            },
        })
        await state.set_state(CollectCreateorderState.awaiting_accept)

    asyncio.run(_add_new_post_draft())

    cleared = asyncio.run(clear_collect_fsm_if_session_matches(state, old_session_id))
    assert cleared is False

    data = asyncio.run(state.get_data())
    assert data.get(COLLECT_SESSION_ID_KEY) == new_session_id
    assert data.get(COLLECT_POST_KEY, {}).get("local_id") == "new-draft"
    assert asyncio.run(state.get_state()) == CollectCreateorderState.awaiting_accept.state


def test_accept_success_still_clears_same_session() -> None:
    state = _FakeFsmContext()
    session_id = asyncio.run(
        start_new_collect_session(state, project_id=uuid4(), order_id=None),
    )
    asyncio.run(state.set_state(CollectCreateorderState.awaiting_accept))

    cleared = asyncio.run(clear_collect_fsm_if_session_matches(state, session_id))
    assert cleared is True
    assert asyncio.run(state.get_state()) is None
    assert asyncio.run(state.get_data()) == {}
