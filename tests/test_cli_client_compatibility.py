"""Regression tests for CLI client compatibility."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeVar

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
from pipeline_dashboard_api_client.cli.protocols import (
    DashboardCommandClient,
    ManagedClient,
)


class RecordingTransport:
    """Transport double returning deterministic responses."""

    def __init__(self) -> None:
        """Initialize the recording transport."""
        self.requests: list[ApiRequest] = []
        self.close_calls = 0

    def execute(
        self,
        request: ApiRequest,
    ) -> ApiResponse[bytes]:
        """Record a request and return a successful response."""
        self.requests.append(request)

        return ApiResponse(
            status_code=200,
            data=b'{"status":"network"}',
            headers={
                "Content-Type": "application/json",
            },
            request_id="request-compatibility-31",
            elapsed_ms=2.5,
        )

    def close(self) -> None:
        """Record transport closure."""
        self.close_calls += 1


class MemoryCacheStore:
    """In-memory cache store for compatibility tests."""

    def __init__(self) -> None:
        """Initialize empty cache storage."""
        self.entries: dict[CacheKey, CacheEntry] = {}

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
        """Write an entry."""
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


ClientT = TypeVar(
    "ClientT",
    bound=DashboardCommandClient,
)


def execute_dashboard(
    client: ClientT,
) -> ApiResponse[bytes]:
    """Execute a dashboard request through the shared client contract."""
    return client.get_dashboard()


def close_managed_client(
    client: ManagedClient,
) -> None:
    """Close a client through the shared lifecycle contract."""
    client.close()


def build_network_client() -> tuple[
    DashboardClient,
    RecordingTransport,
]:
    """Build a plain dashboard client."""
    config = ApiClientConfig(
        base_url="https://dashboard.example.com",
    )
    transport = RecordingTransport()

    client = DashboardClient(
        config,
        transport=transport,
    )

    return client, transport


def build_cached_client() -> tuple[
    CachedDashboardClient,
    DashboardClient,
    RecordingTransport,
    MemoryCacheStore,
]:
    """Build a cached dashboard client."""
    network_client, transport = build_network_client()
    store = MemoryCacheStore()

    cached_client = CachedDashboardClient(
        network_client,
        CacheService(store),
        CachePolicy(ttl_seconds=300),
        now_provider=lambda: datetime(
            2026,
            7,
            15,
            20,
            0,
            tzinfo=UTC,
        ),
    )

    return (
        cached_client,
        network_client,
        transport,
        store,
    )


def test_plain_client_satisfies_command_contract() -> None:
    """DashboardClient works through DashboardCommandClient."""
    client, transport = build_network_client()

    response = execute_dashboard(client)

    assert response.data == b'{"status":"network"}'
    assert len(transport.requests) == 1
    assert transport.requests[0].path == "/dashboard"

    client.close()


def test_cached_client_satisfies_command_contract() -> None:
    """CachedDashboardClient works through DashboardCommandClient."""
    (
        cached_client,
        network_client,
        transport,
        store,
    ) = build_cached_client()

    response = execute_dashboard(cached_client)

    assert response.data == b'{"status":"network"}'
    assert len(transport.requests) == 1
    assert len(store.entries) == 1

    cached_client.close()

    assert network_client.is_closed is True


def test_cached_client_reuses_fresh_response() -> None:
    """A second request uses fresh cache without another network call."""
    (
        cached_client,
        _,
        transport,
        store,
    ) = build_cached_client()

    first_response = execute_dashboard(cached_client)
    second_response = execute_dashboard(cached_client)

    assert first_response.data == b'{"status":"network"}'
    assert second_response.data == b'{"status":"network"}'
    assert second_response.headers["X-RADAR-Cache"] == "fresh"
    assert second_response.elapsed_ms == 0.0

    assert len(transport.requests) == 1
    assert len(store.entries) == 1

    cached_client.close()


def test_both_clients_satisfy_managed_lifecycle_contract() -> None:
    """Plain and cached clients can be closed through ManagedClient."""
    plain_client, _ = build_network_client()

    (
        cached_client,
        network_client,
        _,
        _,
    ) = build_cached_client()

    close_managed_client(plain_client)
    close_managed_client(cached_client)

    assert plain_client.is_closed is True
    assert cached_client.is_closed is True
    assert network_client.is_closed is True


def test_cached_client_close_is_idempotent() -> None:
    """Cached client lifecycle remains safe under repeated closure."""
    (
        cached_client,
        network_client,
        _,
        _,
    ) = build_cached_client()

    cached_client.close()
    cached_client.close()

    assert cached_client.is_closed is True
    assert network_client.is_closed is True
