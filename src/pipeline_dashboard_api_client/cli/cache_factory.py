"""Factory for composing cache-aware CLI clients."""

from __future__ import annotations

from pipeline_dashboard_api_client.cache_service import CacheService
from pipeline_dashboard_api_client.cache_store import FileCacheStore
from pipeline_dashboard_api_client.cached_client import CachedDashboardClient
from pipeline_dashboard_api_client.cli.cache_wiring import (
    CacheWiringResult,
)
from pipeline_dashboard_api_client.cli.config import CliRuntimeConfig
from pipeline_dashboard_api_client.client import DashboardClient

CacheAwareDashboardClient = DashboardClient | CachedDashboardClient
DashboardCacheWiring = CacheWiringResult[
    CacheAwareDashboardClient,
    FileCacheStore,
]


def build_cache_wiring(
    runtime_config: CliRuntimeConfig,
    network_client: DashboardClient,
    /,
) -> DashboardCacheWiring:
    """Compose an optional filesystem cache around a network client."""
    if not runtime_config.cache.enabled:
        return CacheWiringResult[
            CacheAwareDashboardClient,
            FileCacheStore,
        ](
            client=network_client,
            cache_store=None,
            cache_enabled=False,
        )

    cache_store = FileCacheStore(
        runtime_config.cache.root,
    )
    cache_service = CacheService(cache_store)

    cached_client = CachedDashboardClient(
        network_client,
        cache_service,
        runtime_config.cache.policy,
        offline_mode=runtime_config.cache.offline_mode,
    )

    return CacheWiringResult[
        CacheAwareDashboardClient,
        FileCacheStore,
    ](
        client=cached_client,
        cache_store=cache_store,
        cache_enabled=True,
    )
