"""Profile-level scrape lease shared by single + bulk runners.

Prevents concurrent writers for the same profile. A generation counter lets a
newer Refresh invalidate in-flight work before it persists results.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Literal

LeaseOwner = Literal["single", "bulk", "deep"]


@dataclass(frozen=True)
class _Lease:
    owner: LeaseOwner
    generation: int


_lock = asyncio.Lock()
_leases: dict[str, _Lease] = {}
_generations: dict[str, int] = {}


def current_generation(profile_id: str) -> int:
    return int(_generations.get(str(profile_id), 0))


def bump_generation(profile_id: str) -> int:
    """Bump and return the new generation for ``profile_id``."""
    pid = str(profile_id)
    nxt = int(_generations.get(pid, 0)) + 1
    _generations[pid] = nxt
    return nxt


def owner_of(profile_id: str) -> LeaseOwner | None:
    lease = _leases.get(str(profile_id))
    return lease.owner if lease else None


def current_owner(profile_id: str) -> LeaseOwner | None:
    """Alias for ``owner_of``."""
    return owner_of(profile_id)


def is_held_by(
    profile_id: str,
    owner: LeaseOwner,
    generation: int | None = None,
) -> bool:
    lease = _leases.get(str(profile_id))
    if lease is None or lease.owner != owner:
        return False
    if generation is not None and lease.generation != int(generation):
        return False
    return True


async def acquire(profile_id: str, owner: LeaseOwner, generation: int) -> bool:
    """Try to take the lease.

    Succeeds when free, already held by the same owner+generation, or when
    ``generation`` is newer than the current holder's (Refresh / re-claim).
    """
    pid = str(profile_id)
    gen = int(generation)
    async with _lock:
        cur = _leases.get(pid)
        if cur is None or (cur.owner == owner and cur.generation == gen):
            _leases[pid] = _Lease(owner=owner, generation=gen)
            return True
        if gen > cur.generation:
            _leases[pid] = _Lease(owner=owner, generation=gen)
            return True
        return False


async def try_acquire(profile_id: str, owner: LeaseOwner, generation: int) -> bool:
    """Alias for ``acquire``."""
    return await acquire(profile_id, owner, generation)


async def release(profile_id: str, owner: LeaseOwner, generation: int) -> None:
    """Release only if this owner+generation still holds the lease."""
    pid = str(profile_id)
    gen = int(generation)
    async with _lock:
        cur = _leases.get(pid)
        if cur is not None and cur.owner == owner and cur.generation == gen:
            _leases.pop(pid, None)


@asynccontextmanager
async def acquire_profile_lease(
    profile_id: str,
    owner: LeaseOwner,
    generation: int,
) -> AsyncIterator[bool]:
    """Async context manager around acquire/release.

    Yields True if the lease was acquired; False if another holder owns it
    (caller should not scrape / write). Release is a no-op when not acquired.
    """
    ok = await acquire(profile_id, owner, generation)
    try:
        yield ok
    finally:
        if ok:
            await release(profile_id, owner, generation)
