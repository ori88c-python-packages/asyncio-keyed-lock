from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass(slots=True)
class _LockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ref_count: int = 0


class AsyncioKeyedLock:
    """A lock that maps arbitrary keys to independent :class:`asyncio.Lock` instances.

    Locks are created on demand and removed automatically once all waiters for
    a given key have finished (reference count drops to zero), keeping memory
    use proportional to the number of keys *currently* in contention.

    Usage::

        lock = AsyncioKeyedLock()

        async with lock("some-key"):
            # only one coroutine at a time holds this lock
            ...

    The implementation is safe for use within a single
    :class:`asyncio.AbstractEventLoop` because asyncio is single-threaded: all
    dict mutations happen in synchronous code between ``await`` points, so no
    additional synchronisation primitive is needed for the bookkeeping itself.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _LockEntry] = {}

        # Signals idleness (no active keys) to wait_for_all() callers.
        # - None:  no active keys; the sentinel for "already idle".
        # - Event: at least one key is active; set and discarded when the
        #          last key is released, waking any suspended wait_for_all().
        self._idle: asyncio.Event | None = None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def active_keys_count(self) -> int:
        """Number of keys currently held or waited on. O(1)."""
        return len(self._entries)

    @property
    def active_keys(self) -> list[str]:
        """Snapshot list of keys currently held or waited on. O(k)."""
        return list(self._entries)

    def __contains__(self, key: object) -> bool:
        """Return ``True`` if *key* is currently held or waited on.

        Enables the natural ``"user:42" in lock`` idiom. O(1).
        """
        return key in self._entries

    # ------------------------------------------------------------------
    # Lock acquisition
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def __call__(self, key: str) -> AsyncIterator[None]:
        """Acquire the lock for *key*, yield, then release and clean up.

        Args:
            key: The key whose associated lock should be acquired.

        Yields:
            Nothing — use as ``async with lock("key"): ...``.
        """
        entry = self._get_entry(key)
        try:
            async with entry.lock:
                yield
        finally:
            self._on_call_completion(key, entry)

    def _get_entry(self, key: str) -> _LockEntry:
        entry = self._entries.get(key)
        if entry is None:
            entry = self._entries[key] = _LockEntry()
            if self._idle is None:
                self._idle = asyncio.Event()

        entry.ref_count += 1
        return entry

    def _on_call_completion(self, key: str, entry: _LockEntry) -> None:
        entry.ref_count -= 1
        if entry.ref_count > 0:
            return

        del self._entries[key]
        if self._entries:
            return

        # All keys released — wake up wait_for_all() callers.
        idle = self._idle
        self._idle = None
        if idle is not None:
            idle.set()

    # ------------------------------------------------------------------
    # Graceful teardown
    # ------------------------------------------------------------------

    async def wait_for_all(self) -> None:
        """Resolve the first time ``active_keys_count`` reaches zero after this
        method is called.

        Returns immediately if no keys are active at the time of the call.

        If new keys are acquired *after* the call but *before* the active-key
        count first reaches zero, those keys must also be released before this
        method resolves. In other words, the resolution trigger is the first
        moment at which the lock holds no active keys — not necessarily the set
        of keys that existed at call time.

        For a strict "wait until the lock is idle and stays idle" guarantee,
        use a loop::

            while lock.active_keys_count > 0:
                await lock.wait_for_all()
        """
        event = self._idle
        if event is None:
            return
        await event.wait()
