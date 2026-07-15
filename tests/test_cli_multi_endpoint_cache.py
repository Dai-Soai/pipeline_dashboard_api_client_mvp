"""Regression tests for multi-endpoint client cache behavior."""

from __future__ import annotations

from datetime import UTC, datetime

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


class EndpointTransport:
    """Transport double returning endpoint-specific response payloads."""

    def __init__(self) -> None:
        """Initialize request recording."""
        self.requests: list[ApiRequest] = []
        self.close_calls = 0

    def execute(
        self,
        request: ApiRequest,
    ) -> ApiResponse[bytes]:
        """Return a deterministic payload for the requested endpoint."""
        self.requests.append(request)

        payloads = {
            "/dashboard": b'{"endpoint":"dashboard"}',
            "/summary": b'{"endpoint":"summary"}',
            "/health": b'{"endpoint":"health"}',
        }

        return ApiResponse(
            status_code=200,
            data=payloads[request.path],
            headers={
                "Content-Type": "application/json",
            },
            request_id=f"request-{request.path.removeprefix('/')}",
            elapsed_ms=3.0,
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


def build_plain_client() -> tuple[
    DashboardClient,
    EndpointTransport,
]:
    """Build a plain dashboard API client."""
    transport = EndpointTransport()

    client = DashboardClient(
        ApiClientConfig(
            base_url="https://dashboard.example.com",
        ),
        transport=transport,
    )

    return client, transport


def build_cached_client() -> tuple[
    CachedDashboardClient,
    EndpointTransport,
    MemoryCacheStore,
]:
    """Build a cached dashboard API client."""
    network_client, transport = build_plain_client()
    store = MemoryCacheStore()

    cached_client = CachedDashboardClient(
        network_client,
        CacheService(store),
        CachePolicy(ttl_seconds=300),
        now_provider=lambda: datetime(
            2026,
            7,
            15,
            21,
            30,
            tzinfo=UTC,
        ),
    )

    return cached_client, transport, store


def test_plain_client_routes_summary_request() -> None:
    """Plain client sends summary requests to the summary endpoint."""
    client, transport = build_plain_client()

    response = client.get_summary()

    assert response.data == b'{"endpoint":"summary"}'
    assert len(transport.requests) == 1
    assert transport.requests[0].path == "/summary"

    client.close()


def test_plain_client_routes_health_request() -> None:
    """Plain client sends health requests to the health endpoint."""
    client, transport = build_plain_client()

    response = client.get_health()

    assert response.data == b'{"endpoint":"health"}'
    assert len(transport.requests) == 1
    assert transport.requests[0].path == "/health"

    client.close()


def test_cached_summary_response_is_reused() -> None:
    """Fresh summary data is reused without a second network request."""
    client, transport, store = build_cached_client()

    first_response = client.get_summary()
    second_response = client.get_summary()

    assert first_response.data == b'{"endpoint":"summary"}'
    assert second_response.data == b'{"endpoint":"summary"}'
    assert second_response.headers["X-RADAR-Cache"] == "fresh"
    assert second_response.elapsed_ms == 0.0

    assert len(transport.requests) == 1
    assert len(store.entries) == 1

    client.close()


def test_cached_health_response_is_reused() -> None:
    """Fresh health data is reused without a second network request."""
    client, transport, store = build_cached_client()

    first_response = client.get_health()
    second_response = client.get_health()

    assert first_response.data == b'{"endpoint":"health"}'
    assert second_response.data == b'{"endpoint":"health"}'
    assert second_response.headers["X-RADAR-Cache"] == "fresh"
    assert second_response.elapsed_ms == 0.0

    assert len(transport.requests) == 1
    assert len(store.entries) == 1

    client.close()


def test_endpoint_cache_entries_are_isolated() -> None:
    """Dashboard, summary, and health use separate cache entries."""
    client, transport, store = build_cached_client()

    dashboard = client.get_dashboard()
    summary = client.get_summary()
    health = client.get_health()

    assert dashboard.data == b'{"endpoint":"dashboard"}'
    assert summary.data == b'{"endpoint":"summary"}'
    assert health.data == b'{"endpoint":"health"}'

    assert [request.path for request in transport.requests] == [
        "/dashboard",
        "/summary",
        "/health",
    ]
    assert len(store.entries) == 3

    client.close()


def test_each_endpoint_reuses_only_its_own_cached_response() -> None:
    """Repeated endpoint calls reuse matching entries without cross-talk."""
    client, transport, store = build_cached_client()

    client.get_dashboard()
    client.get_summary()
    client.get_health()

    cached_dashboard = client.get_dashboard()
    cached_summary = client.get_summary()
    cached_health = client.get_health()

    assert cached_dashboard.data == b'{"endpoint":"dashboard"}'
    assert cached_summary.data == b'{"endpoint":"summary"}'
    assert cached_health.data == b'{"endpoint":"health"}'

    assert cached_dashboard.headers["X-RADAR-Cache"] == "fresh"
    assert cached_summary.headers["X-RADAR-Cache"] == "fresh"
    assert cached_health.headers["X-RADAR-Cache"] == "fresh"

    assert len(transport.requests) == 3
    assert len(store.entries) == 3

    client.close()
