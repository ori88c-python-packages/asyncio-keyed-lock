"""Mutual exclusion tests: proof that same-key executions never overlap."""

from __future__ import annotations

import asyncio

from asyncio_keyed_lock import AsyncioKeyedLock


async def test_same_key_prevents_concurrent_execution() -> None:
    lock = AsyncioKeyedLock()
    in_critical_section = False
    violations = 0

    async def task() -> None:
        nonlocal in_critical_section, violations
        async with lock("shared"):
            if in_critical_section:
                violations += 1
            in_critical_section = True
            await asyncio.sleep(0)
            in_critical_section = False

    await asyncio.gather(*(task() for _ in range(10)))
    assert violations == 0
