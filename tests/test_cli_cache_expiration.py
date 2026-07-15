"""Regression tests for cache TTL expiration and refresh behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pipeline_dashboard_api_client import (
    ApiClientConfig,
    ApiRequest,
    ApiResponse,
    CachedDashboardClient,
    DashboardClient,
)
from pipeline_dashboard_api_client.cache_contracts import (
    CacheEntry,
    CacheKey,
    CachePolicy,
)
from pipeline_dashboard_api_client.cache_service import CacheService


class MutableClock:
    """Controllable clock for deterministic TTL tests."""

    def __init__(self) -> None:
        """Initialize the clock at a fixed point in time."""
        self.current = datetime(
            2026,
            7,
            15,
            22,
            0,
            tzinfo=UTC,
        )

    def now(self) -> datetime:
        """Return the current test time."""
        return self.current

    def advance(self, *, seconds: int) -> None:
        """Advance the current test time."""
        self.current += timedelta(seconds=seconds)


class SequencedTransport:
    """Transport returning a distinct payload for every network request."""

    def __init__(self) -> None:
        """Initialize request recording."""
        self.requests: list[ApiRequest] = []
        self.close_calls = 0

    def execute(
        self,
        request: ApiRequest,
    ) -> ApiResponse[bytes]:
        """Return a response containing the network request sequence."""
        self.requests.append(request)
        sequence = len(self.requests)

        return ApiResponse(
            status_code=200,
            data=f'{{"network_sequence":{sequence}}}'.encode(),
            headers={
                "Content-Type": "application/json",
            },
            request_id=f"request-cache-expiration-{sequence}",
            elapsed_ms=4.0,
        )

    def close(self) -> None:
        """Record transport closure."""
        self.close_calls += 1


class MemoryCacheStore:
    """Minimal in-memory cache store."""

    def __init__(self) -> None:
        """Initialize empty cache storage."""
        self.entries: dict[CacheKey, CacheEntry] = {}

    def read(
        self,
        key: CacheKey,
    ) -> CacheEntry | None:
        """Read a cached entry."""
        return self.entries.get(key)

    def write(
        self,
        entry: CacheEntry,
    ) -> object:
        """Persist a cached entry."""
        self.entries[entry.key] = entry
        return entry.key

    def delete(
        self,
        key: CacheKey,
    ) -> bool:
        """Delete a cached entry."""
        return self.entries.pop(key, None) is not None

    def clear(self) -> int:
        """Clear all cached entries."""
        count = len(self.entries)
        self.entries.clear()
        return count


def build_cached_client() -> tuple[
    CachedDashboardClient,
    SequencedTransport,
    MemoryCacheStore,
    MutableClock,
]:
    """Build a cached client with a controllable clock."""
    transport = SequencedTransport()
    store = MemoryCacheStore()
    clock = MutableClock()

    network_client = DashboardClient(
        ApiClientConfig(
            base_url="https://dashboard.example.com",
        ),
        transport=transport,
    )

    cached_client = CachedDashboardClient(
        network_client,
        CacheService(store),
        CachePolicy(ttl_seconds=60),
        now_provider=clock.now,
    )

    return cached_client, transport, store, clock


def test_response_within_ttl_uses_fresh_cache() -> None:
    """A response remains reusable while its TTL has not expired."""
    client, transport, store, clock = build_cached_client()

    first_response = client.get_dashboard()

    clock.advance(seconds=59)

    second_response = client.get_dashboard()

    assert first_response.data == b'{"network_sequence":1}'
    assert second_response.data == b'{"network_sequence":1}'
    assert second_response.headers["X-RADAR-Cache"] == "fresh"
    assert second_response.elapsed_ms == 0.0

    assert len(transport.requests) == 1
    assert len(store.entries) == 1

    client.close()


def test_expired_response_triggers_network_refresh() -> None:
    """An expired cache entry causes the client to request fresh data."""
    client, transport, store, clock = build_cached_client()

    first_response = client.get_dashboard()

    clock.advance(seconds=61)

    refreshed_response = client.get_dashboard()

    assert first_response.data == b'{"network_sequence":1}'
    assert refreshed_response.data == b'{"network_sequence":2}'

    assert len(transport.requests) == 2
    assert len(store.entries) == 1

    client.close()


def test_refreshed_response_becomes_new_fresh_cache_entry() -> None:
    """A refreshed network response is cached for later reuse."""
    client, transport, store, clock = build_cached_client()

    initial_response = client.get_dashboard()

    clock.advance(seconds=61)

    refreshed_response = client.get_dashboard()
    cached_refreshed_response = client.get_dashboard()

    assert initial_response.data == b'{"network_sequence":1}'
    assert refreshed_response.data == b'{"network_sequence":2}'
    assert cached_refreshed_response.data == b'{"network_sequence":2}'

    assert cached_refreshed_response.headers["X-RADAR-Cache"] == "fresh"
    assert cached_refreshed_response.elapsed_ms == 0.0

    assert len(transport.requests) == 2
    assert len(store.entries) == 1

    client.close()


def test_repeated_expiration_produces_successive_refreshes() -> None:
    """Each completed TTL window permits another network refresh."""
    client, transport, store, clock = build_cached_client()

    first_response = client.get_dashboard()

    clock.advance(seconds=61)
    second_response = client.get_dashboard()

    clock.advance(seconds=61)
    third_response = client.get_dashboard()

    assert first_response.data == b'{"network_sequence":1}'
    assert second_response.data == b'{"network_sequence":2}'
    assert third_response.data == b'{"network_sequence":3}'

    assert len(transport.requests) == 3
    assert len(store.entries) == 1

    client.close()
