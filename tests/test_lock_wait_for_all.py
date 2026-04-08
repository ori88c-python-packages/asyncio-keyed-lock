"""Tests for wait_for_all: immediate return, blocking, and resolution semantics."""

from __future__ import annotations

import asyncio

from asyncio_keyed_lock import AsyncioKeyedLock


async def test_wait_for_all_resolves_immediately_when_idle() -> None:
    lock = AsyncioKeyedLock()
    await lock.wait_for_all()
    assert lock.active_keys_count == 0


async def test_wait_for_all_blocks_until_all_released() -> None:
    lock = AsyncioKeyedLock()
    release_a = asyncio.Event()
    release_b = asyncio.Event()
    wait_resolved = False

    async def hold(key: str, release: asyncio.Event) -> None:
        async with lock(key):
            await release.wait()

    task_a = asyncio.create_task(hold("a", release_a))
    task_b = asyncio.create_task(hold("b", release_b))
    await asyncio.sleep(0)

    async def waiter() -> None:
        nonlocal wait_resolved
        await lock.wait_for_all()
        wait_resolved = True

    wait_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    assert not wait_resolved

    release_a.set()
    await task_a
    await asyncio.sleep(0)
    assert not wait_resolved

    release_b.set()
    await task_b
    await asyncio.sleep(0)
    assert wait_resolved

    await wait_task


async def test_wait_for_all_includes_later_keys() -> None:
    """Keys acquired after wait_for_all is called also block resolution.

    This is a deliberate trade-off of the single shared Event design:
    wait_for_all resolves when _entries is empty, regardless of when
    individual keys were first acquired.
    """
    lock = AsyncioKeyedLock()
    release_original = asyncio.Event()
    release_new = asyncio.Event()
    wait_resolved = False

    async def hold(key: str, release: asyncio.Event) -> None:
        async with lock(key):
            await release.wait()

    original_task = asyncio.create_task(hold("original", release_original))
    await asyncio.sleep(0)

    async def waiter() -> None:
        nonlocal wait_resolved
        await lock.wait_for_all()
        wait_resolved = True

    wait_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    assert not wait_resolved

    new_task = asyncio.create_task(hold("new", release_new))
    await asyncio.sleep(0)
    assert not wait_resolved

    # Releasing the original key is not enough — "new" still holds.
    release_original.set()
    await original_task
    await asyncio.sleep(0)
    assert not wait_resolved

    # Only after all keys are released does wait_for_all resolve.
    release_new.set()
    await new_task
    await asyncio.sleep(0)
    assert wait_resolved

    await wait_task
