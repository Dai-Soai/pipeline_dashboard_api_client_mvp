"""Tests for CLI dependency factory."""

from pathlib import Path

from pipeline_dashboard_api_client import (
    CachedDashboardClient,
    DashboardClient,
    HttpTransport,
    ResponseParser,
)
from pipeline_dashboard_api_client.cli.config import (
    CliCacheConfig,
    CliRuntimeConfig,
    OutputMode,
)
from pipeline_dashboard_api_client.cli.factory import (
    CliDependencies,
    build_dependencies,
)
from pipeline_dashboard_api_client.contracts import ApiClientConfig


def build_runtime_config(
    *,
    cache_enabled: bool = False,
    cache_root: Path | None = None,
) -> CliRuntimeConfig:
    """Build reusable CLI runtime configuration."""
    root = (
        cache_root
        if cache_root is not None
        else Path("~/.cache/radar-dashboard-client")
    )

    return CliRuntimeConfig(
        client=ApiClientConfig(
            base_url="https://dashboard.example.com",
            timeout_seconds=3.0,
            max_retries=4,
            default_headers={
                "Authorization": "Bearer test",
            },
        ),
        output_mode=OutputMode.PRETTY,
        cache=CliCacheConfig(
            root=root,
            enabled=cache_enabled,
        ),
    )


def test_build_dependencies_creates_runtime_components() -> None:
    """Factory creates the client, parser, and HTTP transport."""
    dependencies = build_dependencies(build_runtime_config())

    assert isinstance(dependencies.client, DashboardClient)
    assert isinstance(dependencies.response_parser, ResponseParser)
    assert isinstance(dependencies.transport, HttpTransport)

    dependencies.close()


def test_factory_preserves_client_configuration() -> None:
    """Factory passes runtime client configuration unchanged."""
    runtime_config = build_runtime_config()

    dependencies = build_dependencies(runtime_config)

    assert isinstance(dependencies.client, DashboardClient)
    assert dependencies.client.config is runtime_config.client
    assert dependencies.transport.config is runtime_config.client

    dependencies.close()


def test_factory_builds_plain_client_when_cache_disabled() -> None:
    """Disabled cache preserves the ordinary dashboard client."""
    dependencies = build_dependencies(
        build_runtime_config(
            cache_enabled=False,
        )
    )

    try:
        assert isinstance(
            dependencies.client,
            DashboardClient,
        )
        assert not isinstance(
            dependencies.client,
            CachedDashboardClient,
        )
    finally:
        dependencies.close()


def test_factory_builds_cached_client_when_cache_enabled(
    tmp_path: Path,
) -> None:
    """Enabled cache wraps the network client."""
    dependencies = build_dependencies(
        build_runtime_config(
            cache_enabled=True,
            cache_root=tmp_path / "cache",
        )
    )

    try:
        assert isinstance(
            dependencies.client,
            CachedDashboardClient,
        )
    finally:
        dependencies.close()


def test_dependencies_start_open() -> None:
    """New dependency bundles begin in an open state."""
    dependencies = build_dependencies(build_runtime_config())

    assert dependencies.is_closed is False
    assert dependencies.client.is_closed is False
    assert dependencies.transport.is_closed is False

    dependencies.close()


def test_close_closes_owned_resources() -> None:
    """Closing dependencies closes both client and transport."""
    dependencies = build_dependencies(build_runtime_config())

    dependencies.close()

    assert dependencies.is_closed is True
    assert dependencies.client.is_closed is True
    assert dependencies.transport.is_closed is True


def test_cached_dependencies_close_client_and_transport(
    tmp_path: Path,
) -> None:
    """Closing cached dependencies closes the complete client chain."""
    dependencies = build_dependencies(
        build_runtime_config(
            cache_enabled=True,
            cache_root=tmp_path / "cache",
        )
    )

    dependencies.close()

    assert dependencies.is_closed is True
    assert dependencies.client.is_closed is True
    assert dependencies.transport.is_closed is True


def test_close_is_idempotent() -> None:
    """Dependency bundles may be closed repeatedly."""
    dependencies = build_dependencies(build_runtime_config())

    dependencies.close()
    dependencies.close()

    assert dependencies.is_closed is True
    assert dependencies.client.is_closed is True
    assert dependencies.transport.is_closed is True


def test_cached_close_is_idempotent(
    tmp_path: Path,
) -> None:
    """Cached dependency bundles may be closed repeatedly."""
    dependencies = build_dependencies(
        build_runtime_config(
            cache_enabled=True,
            cache_root=tmp_path / "cache",
        )
    )

    dependencies.close()
    dependencies.close()

    assert dependencies.is_closed is True
    assert dependencies.client.is_closed is True
    assert dependencies.transport.is_closed is True


def test_context_manager_closes_resources() -> None:
    """Context manager exit releases all owned resources."""
    with build_dependencies(build_runtime_config()) as dependencies:
        assert dependencies.is_closed is False
        assert dependencies.client.is_closed is False
        assert dependencies.transport.is_closed is False

    assert dependencies.is_closed is True
    assert dependencies.client.is_closed is True
    assert dependencies.transport.is_closed is True


def test_closed_dependencies_reject_context_reentry() -> None:
    """Closed dependency bundles cannot be entered again."""
    dependencies = build_dependencies(build_runtime_config())
    dependencies.close()

    try:
        dependencies.__enter__()
    except RuntimeError as error:
        assert str(error) == "CLI dependencies are closed"
    else:
        raise AssertionError("expected RuntimeError")


def test_dependency_bundle_accepts_explicit_components() -> None:
    """Dependency bundle can hold explicitly assembled components."""
    config = ApiClientConfig(
        base_url="https://dashboard.example.com",
    )
    transport = HttpTransport(config)
    client = DashboardClient(
        config,
        transport=transport,
    )
    parser = ResponseParser()

    dependencies = CliDependencies(
        client=client,
        response_parser=parser,
        transport=transport,
    )

    assert dependencies.client is client
    assert dependencies.response_parser is parser
    assert dependencies.transport is transport

    dependencies.close()
