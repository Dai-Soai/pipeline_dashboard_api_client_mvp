"""Regression tests for stale-cache offline fallback behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipeline_dashboard_api_client import (
    ApiClientConfig,
    ApiErrorPayload,
    ApiRequest,
    ApiResponse,
    CachedDashboardClient,
    DashboardApiClientError,
    DashboardClient,
    ErrorKind,
    OfflineMode,
)
from pipeline_dashboard_api_client.cache_contracts import (
    CacheEntry,
    CacheKey,
    CachePolicy,
)
from pipeline_dashboard_api_client.cache_service import CacheService

NOW = datetime(
    2026,
    7,
    15,
    22,
    30,
    tzinfo=UTC,
)


def build_client_error(
    kind: ErrorKind,
) -> DashboardApiClientError:
    """Build a normalized client error using the public contract."""
    return DashboardApiClientError(
        ApiErrorPayload(
            kind=kind,
            message=f"controlled client error: {kind.value}",
        )
    )


class FailingTransport:
    """Transport double raising a configured normalized client error."""

    def __init__(
        self,
        *,
        kind: ErrorKind,
    ) -> None:
        """Initialize the failing transport."""
        self.error = build_client_error(kind)
        self.requests: list[ApiRequest] = []
        self.close_calls = 0

    def execute(
        self,
        request: ApiRequest,
    ) -> ApiResponse[bytes]:
        """Record the request and raise the configured error."""
        self.requests.append(request)
        raise self.error

    def close(self) -> None:
        """Record transport closure."""
        self.close_calls += 1


class MemoryCacheStore:
    """Minimal in-memory cache store."""

    def __init__(self) -> None:
        """Initialize empty cache storage."""
        self.entries: dict[CacheKey, CacheEntry] = {}
        self.write_calls = 0

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
        self.write_calls += 1
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


def build_key(
    resource: str = "dashboard",
) -> CacheKey:
    """Build the cache key used by CachedDashboardClient."""
    return CacheKey(
        namespace="radar-dashboard-api-client",
        resource=resource,
    )


def seed_stale_entry(
    store: MemoryCacheStore,
    *,
    resource: str = "dashboard",
) -> CacheEntry:
    """Seed an entry older than the configured TTL."""
    key = build_key(resource)

    entry = CacheEntry(
        key=key,
        content=b'{"status":"stale-cache"}',
        stored_at=NOW - timedelta(seconds=61),
        status_code=206,
        headers={
            "X-Origin": "cached",
        },
        request_id="request-stale-cache-31",
    )
    store.entries[key] = entry

    return entry


def build_failing_cached_client(
    *,
    error_kind: ErrorKind,
    offline_mode: OfflineMode,
    seed_stale: bool = True,
) -> tuple[
    CachedDashboardClient,
    FailingTransport,
    MemoryCacheStore,
]:
    """Build a cached client whose network transport always fails."""
    store = MemoryCacheStore()

    if seed_stale:
        seed_stale_entry(store)

    transport = FailingTransport(
        kind=error_kind,
    )

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
        offline_mode=offline_mode,
        now_provider=lambda: NOW,
    )

    return cached_client, transport, store


@pytest.mark.parametrize(
    "error_kind",
    [
        ErrorKind.CONNECTION,
        ErrorKind.TIMEOUT,
    ],
)
def test_stale_cache_is_served_for_eligible_offline_errors(
    error_kind: ErrorKind,
) -> None:
    """Connection and timeout failures may use stale cache offline."""
    client, transport, store = build_failing_cached_client(
        error_kind=error_kind,
        offline_mode=OfflineMode.STALE_ON_ERROR,
    )

    response = client.get_dashboard()

    assert response.status_code == 206
    assert response.data == b'{"status":"stale-cache"}'
    assert response.request_id == "request-stale-cache-31"
    assert response.elapsed_ms == 0.0
    assert response.headers == {
        "X-Origin": "cached",
        "X-RADAR-Cache": "stale",
        "X-RADAR-Offline": "true",
    }

    assert len(transport.requests) == 1
    assert transport.requests[0].path == "/dashboard"
    assert store.write_calls == 0
    assert len(store.entries) == 1

    client.close()


def test_disabled_offline_mode_propagates_connection_error() -> None:
    """Disabled offline mode never serves stale cache after failure."""
    client, transport, store = build_failing_cached_client(
        error_kind=ErrorKind.CONNECTION,
        offline_mode=OfflineMode.DISABLED,
    )

    with pytest.raises(DashboardApiClientError) as captured:
        client.get_dashboard()

    assert captured.value is transport.error
    assert len(transport.requests) == 1
    assert store.write_calls == 0
    assert len(store.entries) == 1

    client.close()


def test_cache_miss_cannot_produce_offline_fallback() -> None:
    """Offline fallback requires an existing stale cache entry."""
    client, transport, store = build_failing_cached_client(
        error_kind=ErrorKind.TIMEOUT,
        offline_mode=OfflineMode.STALE_ON_ERROR,
        seed_stale=False,
    )

    with pytest.raises(DashboardApiClientError) as captured:
        client.get_dashboard()

    assert captured.value is transport.error
    assert len(transport.requests) == 1
    assert store.entries == {}
    assert store.write_calls == 0

    client.close()


def test_fresh_cache_skips_failing_network_entirely() -> None:
    """A fresh entry is returned before the network path is attempted."""
    client, transport, store = build_failing_cached_client(
        error_kind=ErrorKind.CONNECTION,
        offline_mode=OfflineMode.STALE_ON_ERROR,
        seed_stale=False,
    )

    key = build_key()
    store.entries[key] = CacheEntry(
        key=key,
        content=b'{"status":"fresh-cache"}',
        stored_at=NOW - timedelta(seconds=30),
        request_id="request-fresh-cache-31",
    )

    response = client.get_dashboard()

    assert response.data == b'{"status":"fresh-cache"}'
    assert response.request_id == "request-fresh-cache-31"
    assert response.headers["X-RADAR-Cache"] == "fresh"
    assert "X-RADAR-Offline" not in response.headers

    assert transport.requests == []
    assert store.write_calls == 0

    client.close()
