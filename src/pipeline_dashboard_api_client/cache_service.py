"""Cache lookup and TTL evaluation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pipeline_dashboard_api_client.cache_contracts import (
    CacheEntry,
    CacheKey,
    CachePolicy,
    CacheStatus,
)


class CacheStore(Protocol):
    """Storage operations required by the cache service."""

    def read(
        self,
        key: CacheKey,
    ) -> CacheEntry | None:
        """Read a cache entry."""
        ...

    def write(
        self,
        entry: CacheEntry,
    ) -> object:
        """Write a cache entry."""
        ...

    def delete(
        self,
        key: CacheKey,
    ) -> bool:
        """Delete a cache entry."""
        ...

    def clear(self) -> int:
        """Clear all managed cache entries."""
        ...


class CacheLookupStatus(StrEnum):
    """Normalized result states for a cache lookup."""

    MISS = "miss"
    FRESH = "fresh"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class CacheLookup:
    """Result of reading and evaluating one cache entry."""

    status: CacheLookupStatus
    entry: CacheEntry | None
    age_seconds: float | None

    def __post_init__(self) -> None:
        """Validate lookup result consistency."""
        if self.status is CacheLookupStatus.MISS:
            if self.entry is not None:
                raise ValueError(
                    "cache miss must not contain an entry"
                )

            if self.age_seconds is not None:
                raise ValueError(
                    "cache miss must not contain an age"
                )

            return

        if self.entry is None:
            raise ValueError(
                "cache hit must contain an entry"
            )

        if self.age_seconds is None:
            raise ValueError(
                "cache hit must contain an age"
            )

        if self.age_seconds < 0:
            raise ValueError(
                "cache age must not be negative"
            )

    @property
    def is_hit(self) -> bool:
        """Return whether the lookup found a cache entry."""
        return self.status is not CacheLookupStatus.MISS

    @property
    def is_fresh(self) -> bool:
        """Return whether the lookup found a fresh entry."""
        return self.status is CacheLookupStatus.FRESH

    @property
    def is_stale(self) -> bool:
        """Return whether the lookup found a stale entry."""
        return self.status is CacheLookupStatus.STALE


class CacheService:
    """Coordinate cache storage and TTL policy evaluation."""

    def __init__(
        self,
        store: CacheStore,
    ) -> None:
        """Initialize the cache service."""
        self._store = store

    @property
    def store(self) -> CacheStore:
        """Return the configured cache store."""
        return self._store

    def lookup(
        self,
        key: CacheKey,
        policy: CachePolicy,
        *,
        now: datetime | None = None,
    ) -> CacheLookup:
        """Read and classify a cache entry as miss, fresh, or stale."""
        entry = self._store.read(key)

        if entry is None:
            return CacheLookup(
                status=CacheLookupStatus.MISS,
                entry=None,
                age_seconds=None,
            )

        age_seconds = entry.age_seconds(now=now)
        entry_status = entry.status(
            policy,
            now=now,
        )

        if entry_status is CacheStatus.FRESH:
            lookup_status = CacheLookupStatus.FRESH
        else:
            lookup_status = CacheLookupStatus.STALE

        return CacheLookup(
            status=lookup_status,
            entry=entry,
            age_seconds=age_seconds,
        )

    def get_usable(
        self,
        key: CacheKey,
        policy: CachePolicy,
        *,
        now: datetime | None = None,
    ) -> CacheEntry | None:
        """Return an entry only when policy permits serving it."""
        lookup = self.lookup(
            key,
            policy,
            now=now,
        )

        if lookup.entry is None:
            return None

        if lookup.is_fresh:
            return lookup.entry

        if lookup.is_stale and policy.allow_stale:
            return lookup.entry

        return None

    def write(
        self,
        entry: CacheEntry,
    ) -> None:
        """Persist one cache entry."""
        self._store.write(entry)

    def delete(
        self,
        key: CacheKey,
    ) -> bool:
        """Delete one cache entry."""
        return self._store.delete(key)

    def clear(self) -> int:
        """Clear every managed cache entry."""
        return self._store.clear()
