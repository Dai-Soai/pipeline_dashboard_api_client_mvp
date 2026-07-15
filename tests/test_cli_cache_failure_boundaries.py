"""Final regression tests for cache and offline failure boundaries."""

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
    23,
    30,
    tzinfo=UTC,
)


def build_key() -> CacheKey:
    """Build the dashboard cache key."""
    return CacheKey(
        namespace="radar-dashboard-api-client",
        resource="dashboard",
    )


def build_client_error(
    kind: ErrorKind,
) -> DashboardApiClientError:
    """Build a normalized dashboard client error."""
    return DashboardApiClientError(
        ApiErrorPayload(
            kind=kind,
            message=f"controlled failure: {kind.value}",
        )
    )


def non_offline_error_kind() -> ErrorKind:
    """Return an error kind not eligible for offline fallback."""
    excluded = {
        ErrorKind.CONNECTION,
        ErrorKind.TIMEOUT,
    }

    return next(
        kind
        for kind in ErrorKind
        if kind not in excluded
    )


class ErrorTransport:
    """Transport double raising one normalized client error."""

    def __init__(
        self,
        *,
        error: DashboardApiClientError,
    ) -> None:
        """Initialize the failing transport."""
        self.error = error
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


class SuccessTransport:
    """Transport double returning one successful response."""

    def __init__(self) -> None:
        """Initialize request recording."""
        self.requests: list[ApiRequest] = []
        self.close_calls = 0

    def execute(
        self,
        request: ApiRequest,
    ) -> ApiResponse[bytes]:
        """Return a deterministic network response."""
        self.requests.append(request)

        return ApiResponse(
            status_code=200,
            data=b'{"status":"network"}',
            headers={
                "Content-Type": "application/json",
            },
            request_id="request-failure-boundary-31",
            elapsed_ms=5.0,
        )

    def close(self) -> None:
        """Record transport closure."""
        self.close_calls += 1


class MemoryCacheStore:
    """Minimal configurable in-memory cache store."""

    def __init__(
        self,
        *,
        fail_read: bool = False,
        fail_write: bool = False,
    ) -> None:
        """Initialize cache storage and failure controls."""
        self.entries: dict[CacheKey, CacheEntry] = {}
        self.fail_read = fail_read
        self.fail_write = fail_write
        self.read_calls = 0
        self.write_calls = 0

    def read(
        self,
        key: CacheKey,
    ) -> CacheEntry | None:
        """Read an entry or raise a controlled storage error."""
        self.read_calls += 1

        if self.fail_read:
            raise RuntimeError("controlled cache read failure")

        return self.entries.get(key)

    def write(
        self,
        entry: CacheEntry,
    ) -> object:
        """Write an entry or raise a controlled storage error."""
        self.write_calls += 1

        if self.fail_write:
            raise RuntimeError("controlled cache write failure")

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


def seed_stale_entry(
    store: MemoryCacheStore,
) -> None:
    """Seed a dashboard entry beyond its TTL."""
    key = build_key()

    store.entries[key] = CacheEntry(
        key=key,
        content=b'{"status":"stale"}',
        stored_at=NOW - timedelta(seconds=61),
        request_id="request-stale-boundary-31",
    )


def build_cached_client(
    *,
    store: MemoryCacheStore,
    transport: ErrorTransport | SuccessTransport,
    policy: CachePolicy | None = None,
    offline_mode: OfflineMode = OfflineMode.DISABLED,
) -> CachedDashboardClient:
    """Build a cached client for failure-boundary tests."""
    network_client = DashboardClient(
        ApiClientConfig(
            base_url="https://dashboard.example.com",
        ),
        transport=transport,
    )

    return CachedDashboardClient(
        network_client,
        CacheService(store),
        policy or CachePolicy(ttl_seconds=60),
        offline_mode=offline_mode,
        now_provider=lambda: NOW,
    )


def test_non_offline_error_is_never_served_from_stale_cache() -> None:
    """Ineligible error kinds propagate despite stale-on-error mode."""
    store = MemoryCacheStore()
    seed_stale_entry(store)

    error = build_client_error(
        non_offline_error_kind()
    )
    transport = ErrorTransport(
        error=error,
    )
    client = build_cached_client(
        store=store,
        transport=transport,
        offline_mode=OfflineMode.STALE_ON_ERROR,
    )

    with pytest.raises(DashboardApiClientError) as captured:
        client.get_dashboard()

    assert captured.value is error
    assert len(transport.requests) == 1
    assert store.write_calls == 0

    client.close()


def test_allow_stale_does_not_enable_offline_fallback_by_itself() -> None:
    """CachePolicy.allow_stale does not replace OfflineMode."""
    store = MemoryCacheStore()
    seed_stale_entry(store)

    error = build_client_error(
        ErrorKind.CONNECTION
    )
    transport = ErrorTransport(
        error=error,
    )
    client = build_cached_client(
        store=store,
        transport=transport,
        policy=CachePolicy(
            ttl_seconds=60,
            allow_stale=True,
        ),
        offline_mode=OfflineMode.DISABLED,
    )

    with pytest.raises(DashboardApiClientError) as captured:
        client.get_dashboard()

    assert captured.value is error
    assert len(transport.requests) == 1
    assert store.write_calls == 0

    client.close()


def test_cache_read_failure_propagates_before_network_call() -> None:
    """Cache lookup failures are not hidden by the network layer."""
    store = MemoryCacheStore(
        fail_read=True,
    )
    transport = SuccessTransport()
    client = build_cached_client(
        store=store,
        transport=transport,
    )

    with pytest.raises(
        RuntimeError,
        match="controlled cache read failure",
    ):
        client.get_dashboard()

    assert store.read_calls == 1
    assert store.write_calls == 0
    assert transport.requests == []

    client.close()


def test_cache_write_failure_propagates_after_network_call() -> None:
    """Cache persistence failures remain visible to callers."""
    store = MemoryCacheStore(
        fail_write=True,
    )
    transport = SuccessTransport()
    client = build_cached_client(
        store=store,
        transport=transport,
    )

    with pytest.raises(
        RuntimeError,
        match="controlled cache write failure",
    ):
        client.get_dashboard()

    assert store.read_calls == 1
    assert store.write_calls == 1
    assert len(transport.requests) == 1
    assert transport.requests[0].path == "/dashboard"
    assert store.entries == {}

    client.close()
