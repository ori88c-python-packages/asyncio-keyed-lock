"""asyncio-keyed-lock — per-key asyncio locking with automatic cleanup."""

from __future__ import annotations

from importlib.metadata import version

from asyncio_keyed_lock._lock import AsyncioKeyedLock

__version__ = version("asyncio-keyed-lock")

__all__ = ["AsyncioKeyedLock", "__version__"]
