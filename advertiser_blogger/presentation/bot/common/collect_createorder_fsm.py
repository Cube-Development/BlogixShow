from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

_chat_accept_locks: dict[int, asyncio.Lock] = {}


def chat_accept_lock(chat_id: int) -> asyncio.Lock:
    lock = _chat_accept_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_accept_locks[chat_id] = lock
    return lock


@asynccontextmanager
async def collect_chat_mutations_lock(chat_id: int) -> AsyncIterator[None]:
    """
    Serializes Accept, Replace, and new-post preview mutations per chat (one process).

    Multi-process: each worker has its own lock. Repo default is one gunicorn worker per app
    instance (build_web.py leaves workers unset). Multiple app replicas behind one bot token
    would need a Redis atomic lock — not implemented here.
    """
    lock = chat_accept_lock(chat_id)
    async with lock:
        yield
