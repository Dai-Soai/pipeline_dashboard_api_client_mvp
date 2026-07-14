"""Tests for the cache-aware dashboard client."""

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


class MemoryCacheStore:
    """In-memory cache storage for cached client tests."""

    def __init__(self) -> None:
        """Initialize empty storage."""
        self.entries: dict[CacheKey, CacheEntry] = {}
        self.write_calls = 0

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
        self.write_calls += 1
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


class RecordingTransport:
    """Transport double returning a configured network response."""

    def __init__(
        self,
        response: ApiResponse[bytes],
    ) -> None:
        """Initialize the transport."""
        self.response = response
        self.requests: list[ApiRequest] = []

    def execute(
        self,
        request: ApiRequest,
    ) -> ApiResponse[bytes]:
        """Record and return the network response."""
        self.requests.append(request)
        return self.response

    def close(self) -> None:
        """Satisfy the transport protocol."""


NOW = datetime(
    2026,
    7,
    14,
    21,
    0,
    tzinfo=UTC,
)


def build_cached_client(
    *,
    store: MemoryCacheStore,
    response: ApiResponse[bytes] | None = None,
    ttl_seconds: float = 300,
    now: datetime = NOW,
) -> tuple[CachedDashboardClient, RecordingTransport]:
    """Build a cache-aware client and recording transport."""
    network_response = response or ApiResponse(
        status_code=200,
        data=b'{"status":"network"}',
        headers={"Content-Type": "application/json"},
        request_id="request-network-31",
        elapsed_ms=15.0,
    )
    transport = RecordingTransport(network_response)
    config = ApiClientConfig(
        base_url="https://dashboard.example.com",
    )
    dashboard_client = DashboardClient(
        config,
        transport=transport,
    )

    cached_client = CachedDashboardClient(
        dashboard_client,
        CacheService(store),
        CachePolicy(ttl_seconds=ttl_seconds),
        now_provider=lambda: now,
    )

    return cached_client, transport


def build_cache_key(
    resource: str,
) -> CacheKey:
    """Build the key used by CachedDashboardClient."""
    return CacheKey(
        namespace="radar-dashboard-api-client",
        resource=resource,
    )


def test_dashboard_cache_miss_calls_network() -> None:
    """A dashboard cache miss invokes the backend."""
    store = MemoryCacheStore()
    client, transport = build_cached_client(store=store)

    response = client.get_dashboard()

    assert response.data == b'{"status":"network"}'
    assert len(transport.requests) == 1
    assert transport.requests[0].path == "/dashboard"


def test_network_response_is_written_to_cache() -> None:
    """Successful network responses become cache entries."""
    store = MemoryCacheStore()
    client, _ = build_cached_client(store=store)

    response = client.get_dashboard()
    entry = store.entries[build_cache_key("dashboard")]

    assert store.write_calls == 1
    assert entry.content == response.data
    assert entry.status_code == response.status_code
    assert entry.request_id == "request-network-31"
    assert entry.stored_at == NOW
    assert entry.metadata == {
        "source": "network",
        "elapsed_ms": 15.0,
    }


def test_fresh_dashboard_cache_skips_network() -> None:
    """Fresh dashboard cache entries avoid backend requests."""
    store = MemoryCacheStore()
    key = build_cache_key("dashboard")
    store.entries[key] = CacheEntry(
        key=key,
        content=b'{"status":"cached"}',
        stored_at=NOW - timedelta(seconds=30),
        request_id="request-cache-31",
    )
    client, transport = build_cached_client(
        store=store,
        ttl_seconds=60,
    )

    response = client.get_dashboard()

    assert response.data == b'{"status":"cached"}'
    assert response.request_id == "request-cache-31"
    assert response.elapsed_ms == 0.0
    assert transport.requests == []
    assert store.write_calls == 0


def test_stale_dashboard_cache_refreshes_network() -> None:
    """Stale entries trigger a backend refresh."""
    store = MemoryCacheStore()
    key = build_cache_key("dashboard")
    store.entries[key] = CacheEntry(
        key=key,
        content=b'{"status":"stale"}',
        stored_at=NOW - timedelta(seconds=61),
    )
    client, transport = build_cached_client(
        store=store,
        ttl_seconds=60,
    )

    response = client.get_dashboard()

    assert response.data == b'{"status":"network"}'
    assert len(transport.requests) == 1
    assert store.entries[key].content == b'{"status":"network"}'


def test_summary_uses_independent_cache_key() -> None:
    """Summary responses use their own cache resource."""
    store = MemoryCacheStore()
    client, transport = build_cached_client(store=store)

    client.get_summary()

    assert transport.requests[0].path == "/summary"
    assert build_cache_key("summary") in store.entries
    assert build_cache_key("dashboard") not in store.entries


def test_health_uses_independent_cache_key() -> None:
    """Health responses use their own cache resource."""
    store = MemoryCacheStore()
    client, transport = build_cached_client(store=store)

    client.get_health()

    assert transport.requests[0].path == "/health"
    assert build_cache_key("health") in store.entries


def test_cached_response_preserves_metadata() -> None:
    """Cached responses preserve status, headers, and request ID."""
    store = MemoryCacheStore()
    key = build_cache_key("summary")
    store.entries[key] = CacheEntry(
        key=key,
        content=b'{"status":"cached"}',
        stored_at=NOW,
        status_code=206,
        headers={"X-Cache-Test": "yes"},
        request_id="request-cached-summary",
    )
    client, transport = build_cached_client(store=store)

    response = client.get_summary()

    assert response.status_code == 206
    assert response.headers == {"X-Cache-Test": "yes"}
    assert response.request_id == "request-cached-summary"
    assert transport.requests == []


def test_query_is_forwarded_on_cache_miss() -> None:
    """Query parameters reach the wrapped network client."""
    store = MemoryCacheStore()
    client, transport = build_cached_client(store=store)

    client.get_dashboard(
        query={
            "limit": 31,
            "active": True,
        }
    )

    assert transport.requests[0].query == {
        "limit": 31,
        "active": True,
    }


def test_headers_are_forwarded_on_cache_miss() -> None:
    """Request headers reach the wrapped network client."""
    store = MemoryCacheStore()
    client, transport = build_cached_client(store=store)

    client.get_health(
        headers={
            "X-Correlation-ID": "cache-31",
        }
    )

    assert transport.requests[0].headers == {
        "X-Correlation-ID": "cache-31",
    }


def test_cache_keys_are_stable_across_clients() -> None:
    """Equivalent clients reuse the same endpoint cache entries."""
    store = MemoryCacheStore()
    first, first_transport = build_cached_client(store=store)
    second, second_transport = build_cached_client(store=store)

    first.get_dashboard()
    second_response = second.get_dashboard()

    assert len(first_transport.requests) == 1
    assert second_transport.requests == []
    assert second_response.data == b'{"status":"network"}'


def test_properties_expose_composed_dependencies() -> None:
    """Cached client exposes its composition dependencies."""
    store = MemoryCacheStore()
    client, _ = build_cached_client(store=store)

    assert isinstance(client.client, DashboardClient)
    assert isinstance(client.cache_service, CacheService)
    assert client.policy.ttl_seconds == 300


def test_naive_now_provider_is_rejected() -> None:
    """Cache timestamps must remain timezone-aware."""
    store = MemoryCacheStore()
    transport = RecordingTransport(
        ApiResponse(
            status_code=200,
            data=b"{}",
        )
    )
    config = ApiClientConfig(
        base_url="https://dashboard.example.com",
    )
    client = CachedDashboardClient(
        DashboardClient(
            config,
            transport=transport,
        ),
        CacheService(store),
        CachePolicy(),
        now_provider=lambda: datetime(
            2026,
            7,
            14,
            21,
            0,
        ),
    )

    try:
        client.get_dashboard()
    except ValueError as error:
        assert "timezone-aware" in str(error)
    else:
        raise AssertionError("expected ValueError")
