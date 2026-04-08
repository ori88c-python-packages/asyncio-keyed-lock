"""Core tests: acquire/release, serialisation, exception safety, cleanup, re-entry."""

from __future__ import annotations

import asyncio

import pytest

from asyncio_keyed_lock import AsyncioKeyedLock


async def test_basic_acquire_and_release() -> None:
    lock = AsyncioKeyedLock()
    async with lock("key"):
        pass


async def test_different_keys_do_not_block_each_other() -> None:
    lock = AsyncioKeyedLock()
    acquired: list[str] = []

    async def grab(key: str) -> None:
        async with lock(key):
            acquired.append(key)

    await asyncio.gather(grab("a"), grab("b"), grab("c"))
    assert sorted(acquired) == ["a", "b", "c"]


async def test_same_key_serialises_access() -> None:
    lock = AsyncioKeyedLock()
    order: list[int] = []

    shared_key = "shared"

    async def task(n: int) -> None:
        async with lock(shared_key):
            order.append(n)
            await asyncio.sleep(0)

    await asyncio.gather(task(1), task(2), task(3))
    assert order == [1, 2, 3]


async def test_exception_inside_lock_still_releases() -> None:
    lock = AsyncioKeyedLock()
    with pytest.raises(RuntimeError):
        async with lock("key"):
            raise RuntimeError("boom")

    # Must be acquirable again after the exception.
    async with lock("key"):
        pass


async def test_cleanup_after_last_release() -> None:
    lock = AsyncioKeyedLock()
    async with lock("temp"):
        assert "temp" in lock
    assert "temp" not in lock
    assert lock.active_keys_count == 0


async def test_no_cleanup_while_waiters_remain() -> None:
    lock = AsyncioKeyedLock()
    entered: asyncio.Event = asyncio.Event()
    waiting: asyncio.Event = asyncio.Event()

    async def holder() -> None:
        async with lock("k"):
            entered.set()
            await waiting.wait()

    async def waiter() -> None:
        await entered.wait()
        # Start waiting for the lock before the holder releases it.
        async with lock("k"):
            pass

    holder_task = asyncio.create_task(holder())
    waiter_task = asyncio.create_task(waiter())
    await entered.wait()
    # While holder has the lock, the key must still be tracked.
    assert "k" in lock
    waiting.set()
    await asyncio.gather(holder_task, waiter_task)
    # After both are done the key must be cleaned up.
    assert "k" not in lock


async def test_reentrant_key_after_cleanup() -> None:
    lock = AsyncioKeyedLock()
    reuse_key = "reuse"
    for _ in range(3):
        async with lock(reuse_key):
            pass
    assert reuse_key not in lock
