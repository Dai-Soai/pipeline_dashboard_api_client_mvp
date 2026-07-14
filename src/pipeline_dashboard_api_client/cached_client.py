"""Cache-aware high-level dashboard API client."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from pipeline_dashboard_api_client.cache_contracts import (
    CacheEntry,
    CacheKey,
    CachePolicy,
)
from pipeline_dashboard_api_client.cache_service import (
    CacheLookup,
    CacheService,
)
from pipeline_dashboard_api_client.client import DashboardClient
from pipeline_dashboard_api_client.contracts import (
    ApiResponse,
    DashboardApiClientError,
    ErrorKind,
    Headers,
    QueryParameters,
)

NowProvider = Callable[[], datetime]


class OfflineMode(StrEnum):
    """Offline fallback behavior for stale cache entries."""

    DISABLED = "disabled"
    STALE_ON_ERROR = "stale_on_error"


class CachedDashboardClient:
    """Serve cached responses and optionally fall back when offline."""

    _CACHE_NAMESPACE = "radar-dashboard-api-client"
    _OFFLINE_ERROR_KINDS = frozenset(
        {
            ErrorKind.CONNECTION,
            ErrorKind.TIMEOUT,
        }
    )

    def __init__(
        self,
        client: DashboardClient,
        cache_service: CacheService,
        policy: CachePolicy,
        *,
        offline_mode: OfflineMode = OfflineMode.DISABLED,
        now_provider: NowProvider | None = None,
    ) -> None:
        """Initialize the cache-aware dashboard client."""
        self._client = client
        self._cache_service = cache_service
        self._policy = policy
        self._offline_mode = offline_mode
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

    @property
    def offline_mode(self) -> OfflineMode:
        """Return the configured offline fallback mode."""
        return self._offline_mode

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
        """Return fresh cache, refresh network, or use stale fallback."""
        key = self._build_key(resource)
        now = self._normalized_now()

        lookup = self._cache_service.lookup(
            key,
            self._policy,
            now=now,
        )

        if lookup.is_fresh and lookup.entry is not None:
            return self._response_from_cache(
                lookup.entry,
                cache_state="fresh",
                offline=False,
            )

        try:
            response = network_call()
        except DashboardApiClientError as error:
            stale_response = self._offline_fallback(
                lookup,
                error=error,
            )

            if stale_response is not None:
                return stale_response

            raise

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

    def _offline_fallback(
        self,
        lookup: CacheLookup,
        *,
        error: DashboardApiClientError,
    ) -> ApiResponse[bytes] | None:
        """Return stale cache for eligible offline failures."""
        if self._offline_mode is OfflineMode.DISABLED:
            return None

        if error.kind not in self._OFFLINE_ERROR_KINDS:
            return None

        if not lookup.is_stale or lookup.entry is None:
            return None

        return self._response_from_cache(
            lookup.entry,
            cache_state="stale",
            offline=True,
        )

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
        *,
        cache_state: str,
        offline: bool,
    ) -> ApiResponse[bytes]:
        """Convert a cached entry back into an API response."""
        headers = dict(entry.headers)
        headers["X-RADAR-Cache"] = cache_state

        if offline:
            headers["X-RADAR-Offline"] = "true"

        return ApiResponse(
            status_code=entry.status_code,
            data=entry.content,
            headers=headers,
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



    @property
    def is_closed(self) -> bool:
        """Return whether the wrapped network client is closed."""
        return self.client.is_closed

    def close(self) -> None:
        """Close the wrapped network client."""
        self.client.close()

def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)
