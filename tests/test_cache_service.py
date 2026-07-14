"""Tests for cache lookup and TTL evaluation."""

from datetime import UTC, datetime, timedelta

import pytest

from pipeline_dashboard_api_client.cache_contracts import (
    CacheEntry,
    CacheKey,
    CachePolicy,
)
from pipeline_dashboard_api_client.cache_service import (
    CacheLookup,
    CacheLookupStatus,
    CacheService,
)


class MemoryCacheStore:
    """In-memory cache store used by service tests."""

    def __init__(
        self,
        entry: CacheEntry | None = None,
    ) -> None:
        """Initialize the memory store."""
        self.entries: dict[CacheKey, CacheEntry] = {}

        if entry is not None:
            self.entries[entry.key] = entry

    def read(
        self,
        key: CacheKey,
    ) -> CacheEntry | None:
        """Read an entry."""
        return self.entries.get(key)

    def write(
        self,
        entry: CacheEntry,
    ) -> object:
        """Persist an entry."""
        self.entries[entry.key] = entry
        return entry.key

    def delete(
        self,
        key: CacheKey,
    ) -> bool:
        """Delete an entry."""
        return self.entries.pop(key, None) is not None

    def clear(self) -> int:
        """Clear all entries."""
        count = len(self.entries)
        self.entries.clear()
        return count


def build_key(
    resource: str = "dashboard",
) -> CacheKey:
    """Build a reusable cache key."""
    return CacheKey(
        namespace="radar-dashboard",
        resource=resource,
    )


def build_entry(
    *,
    resource: str = "dashboard",
    stored_at: datetime | None = None,
) -> CacheEntry:
    """Build a reusable cache entry."""
    return CacheEntry(
        key=build_key(resource),
        content=b'{"status":"healthy"}',
        stored_at=(
            datetime(
                2026,
                7,
                14,
                20,
                0,
                tzinfo=UTC,
            )
            if stored_at is None
            else stored_at
        ),
    )


def test_cache_lookup_miss_contract() -> None:
    """A valid miss contains neither entry nor age."""
    lookup = CacheLookup(
        status=CacheLookupStatus.MISS,
        entry=None,
        age_seconds=None,
    )

    assert lookup.is_hit is False
    assert lookup.is_fresh is False
    assert lookup.is_stale is False


@pytest.mark.parametrize(
    ("entry", "age_seconds"),
    [
        (build_entry(), None),
        (None, 10.0),
    ],
)
def test_cache_hit_requires_entry_and_age(
    entry: CacheEntry | None,
    age_seconds: float | None,
) -> None:
    """Cache hit results require both entry and age."""
    with pytest.raises(ValueError):
        CacheLookup(
            status=CacheLookupStatus.FRESH,
            entry=entry,
            age_seconds=age_seconds,
        )


def test_cache_miss_rejects_entry() -> None:
    """Miss results cannot accidentally carry data."""
    with pytest.raises(
        ValueError,
        match="must not contain an entry",
    ):
        CacheLookup(
            status=CacheLookupStatus.MISS,
            entry=build_entry(),
            age_seconds=None,
        )


def test_lookup_returns_miss() -> None:
    """Missing stored entries are classified as cache misses."""
    store = MemoryCacheStore()
    service = CacheService(store)

    lookup = service.lookup(
        build_key(),
        CachePolicy(),
    )

    assert lookup.status is CacheLookupStatus.MISS
    assert lookup.entry is None
    assert lookup.age_seconds is None


def test_lookup_returns_fresh_entry() -> None:
    """Entries inside TTL are classified as fresh."""
    entry = build_entry()
    service = CacheService(
        MemoryCacheStore(entry)
    )
    now = entry.stored_at + timedelta(seconds=30)

    lookup = service.lookup(
        entry.key,
        CachePolicy(ttl_seconds=60),
        now=now,
    )

    assert lookup.status is CacheLookupStatus.FRESH
    assert lookup.entry is entry
    assert lookup.age_seconds == 30.0
    assert lookup.is_hit is True
    assert lookup.is_fresh is True


def test_lookup_returns_stale_entry() -> None:
    """Entries beyond TTL are classified as stale."""
    entry = build_entry()
    service = CacheService(
        MemoryCacheStore(entry)
    )
    now = entry.stored_at + timedelta(seconds=61)

    lookup = service.lookup(
        entry.key,
        CachePolicy(ttl_seconds=60),
        now=now,
    )

    assert lookup.status is CacheLookupStatus.STALE
    assert lookup.entry is entry
    assert lookup.age_seconds == 61.0
    assert lookup.is_stale is True


def test_exact_ttl_boundary_is_fresh() -> None:
    """An entry remains fresh at the exact TTL boundary."""
    entry = build_entry()
    service = CacheService(
        MemoryCacheStore(entry)
    )
    now = entry.stored_at + timedelta(seconds=60)

    lookup = service.lookup(
        entry.key,
        CachePolicy(ttl_seconds=60),
        now=now,
    )

    assert lookup.status is CacheLookupStatus.FRESH


def test_get_usable_returns_fresh_entry() -> None:
    """Fresh cache entries are always usable."""
    entry = build_entry()
    service = CacheService(
        MemoryCacheStore(entry)
    )

    result = service.get_usable(
        entry.key,
        CachePolicy(ttl_seconds=60),
        now=entry.stored_at + timedelta(seconds=10),
    )

    assert result is entry


def test_get_usable_rejects_stale_entry_by_default() -> None:
    """Stale entries are hidden by strict cache policies."""
    entry = build_entry()
    service = CacheService(
        MemoryCacheStore(entry)
    )

    result = service.get_usable(
        entry.key,
        CachePolicy(ttl_seconds=60),
        now=entry.stored_at + timedelta(seconds=61),
    )

    assert result is None


def test_get_usable_allows_stale_entry() -> None:
    """Stale entries may be served when policy explicitly permits it."""
    entry = build_entry()
    service = CacheService(
        MemoryCacheStore(entry)
    )

    result = service.get_usable(
        entry.key,
        CachePolicy(
            ttl_seconds=60,
            allow_stale=True,
        ),
        now=entry.stored_at + timedelta(hours=1),
    )

    assert result is entry


def test_get_usable_returns_none_for_miss() -> None:
    """Cache misses never produce usable content."""
    service = CacheService(
        MemoryCacheStore()
    )

    result = service.get_usable(
        build_key(),
        CachePolicy(),
    )

    assert result is None


def test_service_delete_delegates_to_store() -> None:
    """Delete behavior is delegated to the configured store."""
    entry = build_entry()
    store = MemoryCacheStore(entry)
    service = CacheService(store)

    assert service.delete(entry.key) is True
    assert service.delete(entry.key) is False


def test_service_clear_returns_deleted_count() -> None:
    """Clear reports the number of removed cache entries."""
    first = build_entry(resource="dashboard")
    second = build_entry(resource="summary")
    store = MemoryCacheStore(first)
    store.entries[second.key] = second
    service = CacheService(store)

    assert service.clear() == 2
    assert store.entries == {}


def test_service_exposes_store() -> None:
    """The configured store remains available for composition."""
    store = MemoryCacheStore()
    service = CacheService(store)

    assert service.store is store
