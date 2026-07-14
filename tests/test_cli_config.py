"""Tests for CLI runtime configuration building."""

import argparse
from pathlib import Path

import pytest

from pipeline_dashboard_api_client.cached_client import OfflineMode
from pipeline_dashboard_api_client.cli.config import (
    CliCacheConfig,
    CliConfigError,
    CliRuntimeConfig,
    OutputMode,
    build_cli_config,
    parse_headers,
)
from pipeline_dashboard_api_client.cli.parser import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    build_parser,
)
from pipeline_dashboard_api_client.contracts import ApiClientConfig


def test_build_cli_config_uses_parser_defaults() -> None:
    """Default parser values produce a valid client configuration."""
    parser = build_parser()
    args = parser.parse_args(["dashboard"])

    config = build_cli_config(args)

    assert config.client.base_url == DEFAULT_BASE_URL
    assert config.client.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert config.client.max_retries == DEFAULT_MAX_RETRIES
    assert config.client.default_headers == {}
    assert config.output_mode is OutputMode.PRETTY


def test_build_cli_config_uses_custom_values() -> None:
    """Explicit CLI values are transferred into client configuration."""
    parser = build_parser()
    args = parser.parse_args(
        [
            "summary",
            "--base-url",
            "https://dashboard.example.com/",
            "--timeout",
            "3.5",
            "--retry",
            "4",
            "--compact",
            "--header",
            "Authorization=Bearer test-token",
        ]
    )

    config = build_cli_config(args)

    assert config.client.base_url == (
        "https://dashboard.example.com"
    )
    assert config.client.timeout_seconds == 3.5
    assert config.client.max_retries == 4
    assert config.client.default_headers == {
        "Authorization": "Bearer test-token"
    }
    assert config.output_mode is OutputMode.COMPACT


def test_parse_headers_accepts_multiple_headers() -> None:
    """Repeated header declarations become a normalized mapping."""
    headers = parse_headers(
        [
            "Authorization=Bearer test",
            "X-Correlation-ID=request-31",
        ]
    )

    assert headers == {
        "Authorization": "Bearer test",
        "X-Correlation-ID": "request-31",
    }


def test_parse_headers_splits_only_first_equals_sign() -> None:
    """Header values may contain additional equals signs."""
    headers = parse_headers(
        ["Authorization=Bearer token=value"]
    )

    assert headers == {
        "Authorization": "Bearer token=value"
    }


def test_parse_headers_strips_whitespace() -> None:
    """Header names and values are stripped."""
    headers = parse_headers(
        [" Authorization = Bearer test "]
    )

    assert headers == {
        "Authorization": "Bearer test"
    }


def test_parse_headers_last_case_insensitive_value_wins() -> None:
    """Later duplicate HTTP headers replace earlier declarations."""
    headers = parse_headers(
        [
            "Authorization=Bearer first",
            "authorization=Bearer second",
        ]
    )

    assert headers == {
        "authorization": "Bearer second"
    }


def test_parse_headers_none_returns_empty_mapping() -> None:
    """Absent header options produce an empty mapping."""
    assert parse_headers(None) == {}


@pytest.mark.parametrize(
    "declaration",
    [
        "Authorization",
        "=Bearer test",
        "Authorization=",
        "   =Bearer test",
        "Authorization=   ",
    ],
)
def test_parse_headers_rejects_invalid_declarations(
    declaration: str,
) -> None:
    """Malformed header declarations are rejected."""
    with pytest.raises(CliConfigError):
        parse_headers([declaration])


def test_build_cli_config_rejects_unsupported_output_mode() -> None:
    """Unsupported output modes cannot enter runtime configuration."""
    args = argparse.Namespace(
        base_url="http://127.0.0.1:8000",
        timeout=10.0,
        retry=2,
        header=None,
        output_mode="yaml",
    )

    with pytest.raises(
        CliConfigError,
        match="unsupported output mode",
    ):
        build_cli_config(args)


def test_build_cli_config_wraps_client_validation_error() -> None:
    """Client contract failures become CLI configuration errors."""
    args = argparse.Namespace(
        base_url="invalid-url",
        timeout=10.0,
        retry=2,
        header=None,
        output_mode="pretty",
    )

    with pytest.raises(
        CliConfigError,
        match="base_url",
    ):
        build_cli_config(args)


def test_build_cli_config_rejects_missing_argument() -> None:
    """Incomplete namespaces fail with a normalized CLI error."""
    args = argparse.Namespace(
        base_url="http://127.0.0.1:8000",
    )

    with pytest.raises(
        CliConfigError,
        match="timeout",
    ):
        build_cli_config(args)


def test_build_cli_config_uses_default_cache_config() -> None:
    """Parser defaults produce enabled fresh-response caching."""
    parser = build_parser()
    args = parser.parse_args(["dashboard"])

    config = build_cli_config(args)

    assert config.cache.enabled is True
    assert config.cache.policy.ttl_seconds == 300.0
    assert config.cache.offline_mode is OfflineMode.DISABLED
    assert config.cache.root == Path(
        "~/.cache/radar-dashboard-client"
    ).expanduser()


def test_build_cli_config_maps_custom_cache_values() -> None:
    """Explicit cache values enter normalized runtime config."""
    parser = build_parser()
    args = parser.parse_args(
        [
            "dashboard",
            "--cache-dir",
            "/tmp/radar-cache",
            "--cache-ttl",
            "45",
        ]
    )

    config = build_cli_config(args)

    assert config.cache.root == Path("/tmp/radar-cache")
    assert config.cache.policy.ttl_seconds == 45.0
    assert config.cache.enabled is True
    assert config.cache.offline_mode is OfflineMode.DISABLED


def test_build_cli_config_maps_offline_mode() -> None:
    """The offline flag selects stale-on-error fallback."""
    parser = build_parser()
    args = parser.parse_args(
        [
            "summary",
            "--offline",
        ]
    )

    config = build_cli_config(args)

    assert config.cache.enabled is True
    assert (
        config.cache.offline_mode
        is OfflineMode.STALE_ON_ERROR
    )


def test_build_cli_config_maps_disabled_cache() -> None:
    """The no-cache flag disables cache composition."""
    parser = build_parser()
    args = parser.parse_args(
        [
            "health",
            "--no-cache",
        ]
    )

    config = build_cli_config(args)

    assert config.cache.enabled is False
    assert config.cache.offline_mode is OfflineMode.DISABLED


def test_runtime_config_preserves_legacy_construction() -> None:
    """Existing callers may omit explicit cache configuration."""
    config = CliRuntimeConfig(
        client=ApiClientConfig(
            base_url="https://dashboard.example.com",
        ),
        output_mode=OutputMode.PRETTY,
    )

    assert isinstance(config.cache, CliCacheConfig)
    assert config.cache.enabled is True


def test_cache_config_rejects_offline_when_disabled() -> None:
    """Offline behavior requires an enabled cache."""
    with pytest.raises(
        ValueError,
        match="requires cache",
    ):
        CliCacheConfig(
            enabled=False,
            offline_mode=OfflineMode.STALE_ON_ERROR,
        )


def test_build_cli_config_rejects_direct_conflicting_namespace() -> None:
    """Invalid manually assembled namespaces are normalized safely."""
    args = argparse.Namespace(
        base_url="http://127.0.0.1:8000",
        timeout=10.0,
        retry=2,
        header=None,
        output_mode="pretty",
        cache_dir="/tmp/radar-cache",
        cache_ttl=300.0,
        cache_enabled=False,
        offline=True,
    )

    with pytest.raises(
        CliConfigError,
        match="requires cache",
    ):
        build_cli_config(args)
