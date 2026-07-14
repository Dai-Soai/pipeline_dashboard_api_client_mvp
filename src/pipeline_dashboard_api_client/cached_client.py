"""Cache-aware high-level dashboard API client."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from pipeline_dashboard_api_client.cache_contracts import (
    CacheEntry,
    CacheKey,
    CachePolicy,
)
from pipeline_dashboard_api_client.cache_service import CacheService
from pipeline_dashboard_api_client.client import DashboardClient
from pipeline_dashboard_api_client.contracts import (
    ApiResponse,
    Headers,
    QueryParameters,
)

NowProvider = Callable[[], datetime]


class CachedDashboardClient:
    """Serve fresh cached responses before contacting the backend."""

    _CACHE_NAMESPACE = "radar-dashboard-api-client"

    def __init__(
        self,
        client: DashboardClient,
        cache_service: CacheService,
        policy: CachePolicy,
        *,
        now_provider: NowProvider | None = None,
    ) -> None:
        """Initialize the cache-aware dashboard client."""
        self._client = client
        self._cache_service = cache_service
        self._policy = policy
        self._now_provider = now_provider or _utc_now

    @property
    def client(self) -> DashboardClient:
        """Return the wrapped network client."""
        return self._client

    @property
    def cache_service(self) -> CacheService:
        """Return the configured cache service."""
        return self._cache_service

    @property
    def policy(self) -> CachePolicy:
        """Return the configured cache policy."""
        return self._policy

    def get_dashboard(
        self,
        *,
        query: QueryParameters | None = None,
        headers: Headers | None = None,
    ) -> ApiResponse[bytes]:
        """Fetch the dashboard response through cache."""
        return self._get(
            resource="dashboard",
            network_call=lambda: self._client.get_dashboard(
                query=query,
                headers=headers,
            ),
        )

    def get_summary(
        self,
        *,
        query: QueryParameters | None = None,
        headers: Headers | None = None,
    ) -> ApiResponse[bytes]:
        """Fetch the summary response through cache."""
        return self._get(
            resource="summary",
            network_call=lambda: self._client.get_summary(
                query=query,
                headers=headers,
            ),
        )

    def get_health(
        self,
        *,
        query: QueryParameters | None = None,
        headers: Headers | None = None,
    ) -> ApiResponse[bytes]:
        """Fetch the health response through cache."""
        return self._get(
            resource="health",
            network_call=lambda: self._client.get_health(
                query=query,
                headers=headers,
            ),
        )

    def _get(
        self,
        *,
        resource: str,
        network_call: Callable[[], ApiResponse[bytes]],
    ) -> ApiResponse[bytes]:
        """Return a fresh cache hit or refresh from the network."""
        key = self._build_key(resource)
        now = self._normalized_now()

        cached_entry = self._cache_service.get_usable(
            key,
            self._policy,
            now=now,
        )

        if cached_entry is not None:
            return self._response_from_cache(cached_entry)

        response = network_call()

        self._cache_service.write(
            CacheEntry(
                key=key,
                content=response.data,
                stored_at=now,
                status_code=response.status_code,
                headers=response.headers,
                request_id=response.request_id,
                metadata={
                    "source": "network",
                    "elapsed_ms": response.elapsed_ms,
                },
            )
        )

        return response

    @classmethod
    def _build_key(
        cls,
        resource: str,
    ) -> CacheKey:
        """Build the stable key for a dashboard endpoint."""
        return CacheKey(
            namespace=cls._CACHE_NAMESPACE,
            resource=resource,
        )

    @staticmethod
    def _response_from_cache(
        entry: CacheEntry,
    ) -> ApiResponse[bytes]:
        """Convert a cached entry back into an API response."""
        return ApiResponse(
            status_code=entry.status_code,
            data=entry.content,
            headers=entry.headers,
            request_id=entry.request_id,
            elapsed_ms=0.0,
        )

    def _normalized_now(self) -> datetime:
        """Return a timezone-aware UTC timestamp."""
        now = self._now_provider()

        if now.tzinfo is None:
            raise ValueError(
                "now_provider must return a timezone-aware datetime"
            )

        return now.astimezone(UTC)


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)
