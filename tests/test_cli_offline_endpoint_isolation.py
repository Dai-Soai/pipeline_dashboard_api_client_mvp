"""Regression tests for endpoint-isolated offline cache fallback."""

from __future__ import annotations

from collections.abc import Callable
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
    0,
    tzinfo=UTC,
)

EndpointCall = Callable[[], ApiResponse[bytes]]


class FailingTransport:
    """Transport double raising one normalized client error."""

    def __init__(
        self,
        *,
        kind: ErrorKind,
    ) -> None:
        """Initialize the failing transport."""
        self.error = DashboardApiClientError(
            ApiErrorPayload(
                kind=kind,
                message=f"controlled endpoint failure: {kind.value}",
            )
        )
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
    resource: str,
) -> CacheKey:
    """Build the stable endpoint cache key."""
    return CacheKey(
        namespace="radar-dashboard-api-client",
        resource=resource,
    )


def seed_stale_entry(
    store: MemoryCacheStore,
    *,
    resource: str,
) -> CacheEntry:
    """Seed a stale cache entry for one endpoint."""
    key = build_key(resource)

    entry = CacheEntry(
        key=key,
        content=f'{{"endpoint":"{resource}","source":"stale"}}'.encode(),
        stored_at=NOW - timedelta(seconds=61),
        status_code=206,
        headers={
            "X-Endpoint": resource,
        },
        request_id=f"request-stale-{resource}-31",
    )
    store.entries[key] = entry

    return entry


def build_client(
    *,
    store: MemoryCacheStore,
    error_kind: ErrorKind = ErrorKind.CONNECTION,
) -> tuple[
    CachedDashboardClient,
    FailingTransport,
]:
    """Build an offline-enabled cached client."""
    transport = FailingTransport(
        kind=error_kind,
    )

    network_client = DashboardClient(
        ApiClientConfig(
            base_url="https://dashboard.example.com",
        ),
        transport=transport,
    )

    client = CachedDashboardClient(
        network_client,
        CacheService(store),
        CachePolicy(ttl_seconds=60),
        offline_mode=OfflineMode.STALE_ON_ERROR,
        now_provider=lambda: NOW,
    )

    return client, transport


def endpoint_call(
    client: CachedDashboardClient,
    resource: str,
) -> EndpointCall:
    """Return the client call corresponding to one endpoint."""
    calls: dict[str, EndpointCall] = {
        "dashboard": client.get_dashboard,
        "summary": client.get_summary,
        "health": client.get_health,
    }

    return calls[resource]


@pytest.mark.parametrize(
    ("resource", "expected_path"),
    [
        ("dashboard", "/dashboard"),
        ("summary", "/summary"),
        ("health", "/health"),
    ],
)
def test_each_endpoint_uses_its_matching_stale_fallback(
    resource: str,
    expected_path: str,
) -> None:
    """Every endpoint falls back only to its matching stale entry."""
    store = MemoryCacheStore()
    seed_stale_entry(
        store,
        resource=resource,
    )
    client, transport = build_client(
        store=store,
        error_kind=ErrorKind.TIMEOUT,
    )

    response = endpoint_call(
        client,
        resource,
    )()

    assert response.status_code == 206
    assert response.data == (
        f'{{"endpoint":"{resource}","source":"stale"}}'.encode()
    )
    assert response.request_id == f"request-stale-{resource}-31"
    assert response.elapsed_ms == 0.0
    assert response.headers == {
        "X-Endpoint": resource,
        "X-RADAR-Cache": "stale",
        "X-RADAR-Offline": "true",
    }

    assert len(transport.requests) == 1
    assert transport.requests[0].path == expected_path
    assert store.write_calls == 0
    assert len(store.entries) == 1

    client.close()


def test_failure_does_not_use_stale_entry_from_another_endpoint() -> None:
    """A summary failure cannot consume a dashboard stale entry."""
    store = MemoryCacheStore()
    seed_stale_entry(
        store,
        resource="dashboard",
    )
    client, transport = build_client(
        store=store,
        error_kind=ErrorKind.CONNECTION,
    )

    with pytest.raises(DashboardApiClientError) as captured:
        client.get_summary()

    assert captured.value is transport.error
    assert len(transport.requests) == 1
    assert transport.requests[0].path == "/summary"

    assert build_key("dashboard") in store.entries
    assert build_key("summary") not in store.entries
    assert store.write_calls == 0

    client.close()
