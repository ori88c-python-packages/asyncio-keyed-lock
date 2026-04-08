"""Introspection tests: active_keys_count, active_keys, and __contains__."""

from __future__ import annotations

import asyncio

from asyncio_keyed_lock import AsyncioKeyedLock


async def test_active_keys_count_during_contention() -> None:
    lock = AsyncioKeyedLock()
    assert lock.active_keys_count == 0

    release_a = asyncio.Event()
    release_b = asyncio.Event()
    release_c = asyncio.Event()

    async def hold(key: str, release: asyncio.Event) -> None:
        async with lock(key):
            await release.wait()

    task_a = asyncio.create_task(hold("a", release_a))
    await asyncio.sleep(0)
    assert lock.active_keys_count == 1
    assert "a" in lock

    task_b = asyncio.create_task(hold("b", release_b))
    await asyncio.sleep(0)
    assert lock.active_keys_count == 2
    assert "b" in lock

    task_c = asyncio.create_task(hold("c", release_c))
    await asyncio.sleep(0)
    assert lock.active_keys_count == 3
    assert "c" in lock

    release_a.set()
    await task_a
    assert lock.active_keys_count == 2
    assert "a" not in lock

    release_b.set()
    await task_b
    assert lock.active_keys_count == 1
    assert "b" not in lock

    release_c.set()
    await task_c
    assert lock.active_keys_count == 0
    assert "c" not in lock


async def test_active_keys_returns_held_keys() -> None:
    lock = AsyncioKeyedLock()
    release_x = asyncio.Event()
    release_y = asyncio.Event()

    async def hold(key: str, release: asyncio.Event) -> None:
        async with lock(key):
            await release.wait()

    task_x = asyncio.create_task(hold("x", release_x))
    task_y = asyncio.create_task(hold("y", release_y))
    await asyncio.sleep(0)

    assert sorted(lock.active_keys) == ["x", "y"]
    assert "x" in lock
    assert "y" in lock
    assert "absent" not in lock

    release_x.set()
    await task_x
    assert lock.active_keys == ["y"]
    assert "x" not in lock
    assert "y" in lock

    release_y.set()
    await task_y
    assert lock.active_keys == []
    assert "y" not in lock
