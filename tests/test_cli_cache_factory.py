"""Tests for cache-aware CLI client composition."""

from __future__ import annotations

from pathlib import Path

from pipeline_dashboard_api_client import (
    ApiClientConfig,
    CachedDashboardClient,
    DashboardClient,
)
from pipeline_dashboard_api_client.cache_store import FileCacheStore
from pipeline_dashboard_api_client.cli.cache_factory import (
    build_cache_wiring,
)
from pipeline_dashboard_api_client.cli.config import (
    CliCacheConfig,
    CliRuntimeConfig,
    OutputMode,
)
from pipeline_dashboard_api_client.transport import HttpTransport


def build_network_client() -> DashboardClient:
    """Build a real network client without issuing HTTP requests."""
    client_config = ApiClientConfig(
        base_url="https://dashboard.example.com",
    )
    transport = HttpTransport(client_config)

    return DashboardClient(
        client_config,
        transport=transport,
    )


def build_runtime_config(
    cache_root: Path,
    *,
    cache_enabled: bool,
) -> CliRuntimeConfig:
    """Build a runtime configuration for cache factory tests."""
    return CliRuntimeConfig(
        client=ApiClientConfig(
            base_url="https://dashboard.example.com",
        ),
        output_mode=OutputMode.COMPACT,
        cache=CliCacheConfig(
            root=cache_root,
            enabled=cache_enabled,
        ),
    )


def test_factory_preserves_plain_client_when_cache_disabled(
    tmp_path: Path,
) -> None:
    """Disabled cache leaves the network client unchanged."""
    network_client = build_network_client()
    runtime_config = build_runtime_config(
        tmp_path,
        cache_enabled=False,
    )

    result = build_cache_wiring(
        runtime_config,
        network_client,
    )

    try:
        assert result.client is network_client
        assert isinstance(result.client, DashboardClient)
        assert result.cache_store is None
        assert result.cache_enabled is False
        assert result.uses_cache is False
    finally:
        network_client.close()


def test_factory_wraps_network_client_when_cache_enabled(
    tmp_path: Path,
) -> None:
    """Enabled cache wraps the network client."""
    network_client = build_network_client()
    runtime_config = build_runtime_config(
        tmp_path,
        cache_enabled=True,
    )

    result = build_cache_wiring(
        runtime_config,
        network_client,
    )

    try:
        assert isinstance(
            result.client,
            CachedDashboardClient,
        )
        assert result.client.client is network_client
        assert isinstance(
            result.cache_store,
            FileCacheStore,
        )
        assert result.cache_store.root == tmp_path
        assert result.cache_enabled is True
        assert result.uses_cache is True
    finally:
        network_client.close()


def test_factory_does_not_create_cache_directory_eagerly(
    tmp_path: Path,
) -> None:
    """Composition does not write cache artifacts before first use."""
    cache_root = tmp_path / "dashboard-cache"
    network_client = build_network_client()
    runtime_config = build_runtime_config(
        cache_root,
        cache_enabled=True,
    )

    result = build_cache_wiring(
        runtime_config,
        network_client,
    )

    try:
        assert result.cache_store is not None
        assert result.cache_store.root == cache_root
        assert cache_root.exists() is False
    finally:
        network_client.close()


def test_factory_creates_independent_wiring_results(
    tmp_path: Path,
) -> None:
    """Repeated composition does not share cache stores or clients."""
    first_network_client = build_network_client()
    second_network_client = build_network_client()

    first_result = build_cache_wiring(
        build_runtime_config(
            tmp_path / "first",
            cache_enabled=True,
        ),
        first_network_client,
    )
    second_result = build_cache_wiring(
        build_runtime_config(
            tmp_path / "second",
            cache_enabled=True,
        ),
        second_network_client,
    )

    try:
        assert first_result is not second_result
        assert first_result.client is not second_result.client
        assert first_result.cache_store is not second_result.cache_store
        assert first_result.cache_store is not None
        assert second_result.cache_store is not None
        assert first_result.cache_store.root == tmp_path / "first"
        assert second_result.cache_store.root == tmp_path / "second"
    finally:
        first_network_client.close()
        second_network_client.close()
