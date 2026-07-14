"""Tests for cached-client lifecycle compatibility."""

from __future__ import annotations

from pathlib import Path

from pipeline_dashboard_api_client import (
    ApiClientConfig,
    CachedDashboardClient,
    DashboardClient,
)
from pipeline_dashboard_api_client.cli.cache_factory import (
    build_cache_wiring,
)
from pipeline_dashboard_api_client.cli.cache_wiring import (
    ManagedClient,
)
from pipeline_dashboard_api_client.cli.config import (
    CliCacheConfig,
    CliRuntimeConfig,
    OutputMode,
)
from pipeline_dashboard_api_client.transport import HttpTransport


def build_network_client() -> DashboardClient:
    """Build a real network client without issuing requests."""
    config = ApiClientConfig(
        base_url="https://dashboard.example.com",
    )
    transport = HttpTransport(config)

    return DashboardClient(
        config,
        transport=transport,
    )


def build_cached_client(
    cache_root: Path,
) -> tuple[
    CachedDashboardClient,
    DashboardClient,
]:
    """Build a cached client and retain its wrapped client."""
    network_client = build_network_client()

    runtime_config = CliRuntimeConfig(
        client=ApiClientConfig(
            base_url="https://dashboard.example.com",
        ),
        output_mode=OutputMode.COMPACT,
        cache=CliCacheConfig(
            root=cache_root,
            enabled=True,
        ),
    )

    result = build_cache_wiring(
        runtime_config,
        network_client,
    )

    assert isinstance(
        result.client,
        CachedDashboardClient,
    )

    return result.client, network_client


def test_cached_client_satisfies_managed_client_protocol(
    tmp_path: Path,
) -> None:
    """Cached clients expose the required lifecycle contract."""
    cached_client, network_client = build_cached_client(
        tmp_path,
    )

    try:
        assert isinstance(
            cached_client,
            ManagedClient,
        )
    finally:
        network_client.close()


def test_cached_client_reports_open_state(
    tmp_path: Path,
) -> None:
    """Cached clients initially reflect an open network client."""
    cached_client, network_client = build_cached_client(
        tmp_path,
    )

    try:
        assert cached_client.is_closed is False
        assert network_client.is_closed is False
    finally:
        network_client.close()


def test_cached_client_close_closes_wrapped_client(
    tmp_path: Path,
) -> None:
    """Closing a cached client closes its network client."""
    cached_client, network_client = build_cached_client(
        tmp_path,
    )

    cached_client.close()

    assert cached_client.is_closed is True
    assert network_client.is_closed is True


def test_cached_client_close_is_idempotent(
    tmp_path: Path,
) -> None:
    """Cached clients may be closed repeatedly."""
    cached_client, network_client = build_cached_client(
        tmp_path,
    )

    cached_client.close()
    cached_client.close()

    assert cached_client.is_closed is True
    assert network_client.is_closed is True
