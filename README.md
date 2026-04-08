# asyncio-keyed-lock

[![CI](https://github.com/ori88c-python-packages/asyncio-keyed-lock/actions/workflows/ci.yml/badge.svg)](https://github.com/ori88c-python-packages/asyncio-keyed-lock/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/asyncio-keyed-lock.svg)](https://pypi.org/project/asyncio-keyed-lock/)
[![Python versions](https://img.shields.io/pypi/pyversions/asyncio-keyed-lock.svg)](https://pypi.org/project/asyncio-keyed-lock/)
[![License](https://img.shields.io/pypi/l/asyncio-keyed-lock.svg)](LICENSE)

Per-key asyncio locking with automatic cleanup and graceful-shutdown support. Zero runtime dependencies.

Internally, `AsyncioKeyedLock` maintains a `dict` that maps keys to regular `asyncio.Lock` instances. Locks are created on demand and evicted automatically when their reference count drops to zero, keeping memory usage proportional to the number of keys *currently* in contention.

## Table of Contents

- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [API](#api)
- [Use Case: Concurrent Batch Processing](#use-case-concurrent-batch-processing)
- [Race Conditions in Single-Threaded asyncio](#race-conditions-in-single-threaded-asyncio)
- [Graceful Teardown](#graceful-teardown)
- [Development](#development)
- [License](#license)

## Key Features

- **Per-key mutual exclusion** using the native `async with lock("key")` idiom — no callbacks, no manual acquire/release.
- **Event-driven eviction** of idle keys. Internal lock entries are removed the moment no coroutine references them, so memory never grows beyond what is actively in use.
- **Graceful teardown** via `wait_for_all()`. Wait for every in-flight critical section to complete before shutting down — useful for application lifecycle hooks and clean test isolation.
- **Introspection** for monitoring and debugging: `active_keys_count`, `active_keys`, and the Pythonic `"key" in lock` containment check.
- **Zero runtime dependencies**. The package uses only the Python standard library (`asyncio`, `dataclasses`, `contextlib`).
- **Fully type-annotated** with a `py.typed` marker ([PEP 561](https://peps.python.org/pep-0561/)). Works out of the box with mypy, pyright, and other type checkers.
- **Tested** on Python 3.10 through 3.14.

## Installation

```bash
pip install asyncio-keyed-lock
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add asyncio-keyed-lock
```

## Quick Start

```python
import asyncio
from asyncio_keyed_lock import AsyncioKeyedLock

lock = AsyncioKeyedLock()

async def process(resource_id: str) -> None:
    async with lock(resource_id):
        # Only one coroutine at a time holds the lock for this resource_id.
        # Different resource_ids proceed concurrently.
        ...

async def main() -> None:
    await asyncio.gather(
        process("user:42"),
        process("user:42"),  # waits for the first one
        process("user:99"),  # proceeds immediately
    )

asyncio.run(main())
```

## API

| Member | Kind | Description |
|---|---|---|
| `lock(key)` | async context manager | Acquire the lock for *key*, yield, then release and clean up. |
| `active_keys_count` | property | Number of keys currently held or waited on. O(1). |
| `active_keys` | property | Snapshot `list` of keys currently held or waited on. O(k). |
| `"key" in lock` | containment check | `True` if *key* is currently held or waited on. O(1). |
| `await lock.wait_for_all()` | async method | Resolve the first time `active_keys_count` reaches zero. See [Graceful Teardown](#graceful-teardown). |

## Use Case: Concurrent Batch Processing

When consuming messages from a system like Apache Kafka, messages within a single partition are delivered in order. If you process them one at a time, per-key ordering is inherently preserved — two messages with the same key never overlap.

**Batch processing** changes the picture. Pulling multiple messages from the same partition and processing them concurrently is significantly faster, but it breaks the per-key serial guarantee: two messages that share a key can now execute in parallel, leading to the same race conditions described [later in this document](#race-conditions-in-single-threaded-asyncio).

An `AsyncioKeyedLock` scoped to each batch restores per-key serialisation while keeping different keys fully concurrent. Combined with `wait_for_all()`, the batch handler can wait until every message has been processed before committing the consumer offset — ensuring no work is lost.

```python
import asyncio
from dataclasses import dataclass

from asyncio_keyed_lock import AsyncioKeyedLock


@dataclass(slots=True)
class Message:
    key: str
    payload: bytes


async def handle_message(msg: Message) -> None:
    # Business logic that must not interleave for the same key.
    ...


async def process_batch(messages: list[Message]) -> None:
    lock = AsyncioKeyedLock()

    async def _process(msg: Message) -> None:
        async with lock(msg.key):
            await handle_message(msg)

    async with asyncio.TaskGroup() as tg:
        for msg in messages:
            tg.create_task(_process(msg))

    # All tasks have completed — safe to commit the batch offset.
```

## Race Conditions in Single-Threaded asyncio

Python's `asyncio` runs in a single thread, but that does **not** prevent race conditions. The reason is that every `await` expression is a **yield point** — a place where the event loop can suspend the current coroutine and run another one.

Synchronous code *between* `await` points executes atomically within a single event-loop iteration and cannot be interleaved. However, any operation that spans **multiple** `await` points (e.g., read-then-write against a database) can be interleaved with other coroutines doing the same thing, leading to inconsistent state.

A keyed lock serialises those multi-`await` operations per key, ensuring that for a given key only one coroutine is inside the critical section at a time — while still allowing unrelated keys to proceed concurrently.

## Graceful Teardown

`wait_for_all()` resolves the first time `active_keys_count` reaches zero after the call. This is useful during application shutdown or between tests to ensure all in-flight work is complete.

```python
# Wait until all currently active keys have been released.
await lock.wait_for_all()
```

If new keys are acquired *after* the call but *before* the count first reaches zero, those keys must also be released before `wait_for_all()` resolves. In other words, the trigger is the first moment the lock holds **no active keys at all** — not the specific set of keys that existed at call time.

For a strict "wait until truly idle" guarantee when new work may keep arriving:

```python
while lock.active_keys_count > 0:
    await lock.wait_for_all()
```

## Development

```bash
git clone https://github.com/ori88c-python-packages/asyncio-keyed-lock.git
cd asyncio-keyed-lock
uv sync

# Run tests
uv run pytest

# Lint and format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy src
```

## License

[Apache 2.0](LICENSE)
