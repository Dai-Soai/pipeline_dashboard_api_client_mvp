"""Tests for the modular CLI argument parser."""

import pytest

from pipeline_dashboard_api_client.cli.parser import (
    DEFAULT_BASE_URL,
    DEFAULT_CACHE_DIR,
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_OUTPUT_MODE,
    DEFAULT_TIMEOUT_SECONDS,
    build_parser,
)


@pytest.mark.parametrize(
    "command",
    [
        "version",
        "dashboard",
        "summary",
        "health",
        "validate",
    ],
)
def test_parser_accepts_supported_commands(
    command: str,
) -> None:
    """Every declared CLI command is accepted."""
    parser = build_parser()

    args = parser.parse_args([command])

    assert args.command == command


def test_api_command_uses_default_options() -> None:
    """API commands receive stable default client options."""
    parser = build_parser()

    args = parser.parse_args(["dashboard"])

    assert args.base_url == DEFAULT_BASE_URL
    assert args.timeout == DEFAULT_TIMEOUT_SECONDS
    assert args.retry == DEFAULT_MAX_RETRIES
    assert args.header is None
    assert args.output_mode == DEFAULT_OUTPUT_MODE


def test_api_command_accepts_custom_options() -> None:
    """API commands accept explicit connection options."""
    parser = build_parser()

    args = parser.parse_args(
        [
            "summary",
            "--base-url",
            "https://dashboard.example.com",
            "--timeout",
            "4.5",
            "--retry",
            "5",
        ]
    )

    assert args.command == "summary"
    assert args.base_url == "https://dashboard.example.com"
    assert args.timeout == 4.5
    assert args.retry == 5


def test_header_option_may_be_repeated() -> None:
    """Repeated header options preserve their input order."""
    parser = build_parser()

    args = parser.parse_args(
        [
            "health",
            "--header",
            "Authorization=Bearer test",
            "--header",
            "X-Correlation-ID=request-31",
        ]
    )

    assert args.header == [
        "Authorization=Bearer test",
        "X-Correlation-ID=request-31",
    ]


def test_pretty_output_mode() -> None:
    """Pretty output mode can be selected explicitly."""
    parser = build_parser()

    args = parser.parse_args(["dashboard", "--pretty"])

    assert args.output_mode == "pretty"


def test_compact_output_mode() -> None:
    """Compact output mode can be selected explicitly."""
    parser = build_parser()

    args = parser.parse_args(["dashboard", "--compact"])

    assert args.output_mode == "compact"


def test_pretty_and_compact_are_mutually_exclusive() -> None:
    """Conflicting output modes are rejected."""
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(
            [
                "dashboard",
                "--pretty",
                "--compact",
            ]
        )

    assert captured.value.code == 2


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "-1",
        "invalid",
    ],
)
def test_timeout_rejects_invalid_values(
    value: str,
) -> None:
    """Timeout requires a positive numeric value."""
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(
            [
                "dashboard",
                "--timeout",
                value,
            ]
        )

    assert captured.value.code == 2


@pytest.mark.parametrize(
    "value",
    [
        "-1",
        "invalid",
    ],
)
def test_retry_rejects_invalid_values(
    value: str,
) -> None:
    """Retry count requires a non-negative integer."""
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(
            [
                "dashboard",
                "--retry",
                value,
            ]
        )

    assert captured.value.code == 2


def test_command_help_exits_successfully() -> None:
    """Command-specific help is available."""
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(["dashboard", "--help"])

    assert captured.value.code == 0


def test_api_command_uses_default_cache_options() -> None:
    """API commands receive stable default cache options."""
    parser = build_parser()

    args = parser.parse_args(["dashboard"])

    assert args.cache_dir == DEFAULT_CACHE_DIR
    assert args.cache_ttl == DEFAULT_CACHE_TTL_SECONDS
    assert args.cache_enabled is True
    assert args.offline is False


def test_api_command_accepts_custom_cache_options() -> None:
    """Cache directory and TTL can be configured explicitly."""
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

    assert args.cache_dir == "/tmp/radar-cache"
    assert args.cache_ttl == 45.0
    assert args.cache_enabled is True


def test_offline_option_enables_offline_mode() -> None:
    """Offline fallback can be enabled explicitly."""
    parser = build_parser()

    args = parser.parse_args(
        [
            "summary",
            "--offline",
        ]
    )

    assert args.offline is True
    assert args.cache_enabled is True


def test_no_cache_option_disables_cache() -> None:
    """Cache can be disabled explicitly."""
    parser = build_parser()

    args = parser.parse_args(
        [
            "health",
            "--no-cache",
        ]
    )

    assert args.cache_enabled is False
    assert args.offline is False


def test_offline_and_no_cache_are_mutually_exclusive() -> None:
    """Offline fallback cannot be combined with disabled cache."""
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(
            [
                "dashboard",
                "--offline",
                "--no-cache",
            ]
        )

    assert captured.value.code == 2


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "-1",
        "invalid",
    ],
)
def test_cache_ttl_rejects_invalid_values(
    value: str,
) -> None:
    """Cache TTL requires a positive numeric value."""
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(
            [
                "dashboard",
                "--cache-ttl",
                value,
            ]
        )

    assert captured.value.code == 2


def test_parser_accepts_cache_status_command() -> None:
    """Cache status is registered as a top-level command."""
    parser = build_parser()

    args = parser.parse_args(["cache-status"])

    assert args.command == "cache-status"
    assert args.cache_dir == DEFAULT_CACHE_DIR
    assert args.output_mode == DEFAULT_OUTPUT_MODE


def test_parser_accepts_cache_clear_command() -> None:
    """Cache clear is registered as a top-level command."""
    parser = build_parser()

    args = parser.parse_args(["cache-clear"])

    assert args.command == "cache-clear"
    assert args.cache_dir == DEFAULT_CACHE_DIR
    assert args.output_mode == DEFAULT_OUTPUT_MODE


def test_cache_command_accepts_custom_directory() -> None:
    """Cache commands accept an explicit cache root."""
    parser = build_parser()

    args = parser.parse_args(
        [
            "cache-status",
            "--cache-dir",
            "/tmp/radar-cache",
        ]
    )

    assert args.cache_dir == "/tmp/radar-cache"


def test_cache_command_accepts_compact_output() -> None:
    """Cache commands support compact JSON output."""
    parser = build_parser()

    args = parser.parse_args(
        [
            "cache-clear",
            "--compact",
        ]
    )

    assert args.output_mode == "compact"


def test_cache_command_does_not_expose_network_options() -> None:
    """Cache commands reject backend-only connection options."""
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(
            [
                "cache-status",
                "--base-url",
                "https://dashboard.example.com",
            ]
        )

    assert captured.value.code == 2


def test_api_command_uses_default_export_options() -> None:
    """API commands do not export unless explicitly requested."""
    parser = build_parser()

    args = parser.parse_args(["dashboard"])

    assert args.output_file is None
    assert args.overwrite is False


def test_api_command_accepts_export_options() -> None:
    """API commands accept output-file and overwrite options."""
    parser = build_parser()

    args = parser.parse_args(
        [
            "summary",
            "--output-file",
            "/tmp/summary.json",
            "--overwrite",
        ]
    )

    assert args.output_file == "/tmp/summary.json"
    assert args.overwrite is True


@pytest.mark.parametrize(
    "command",
    [
        "cache-status",
        "cache-clear",
    ],
)
def test_cache_commands_do_not_expose_export_options(
    command: str,
) -> None:
    """Cache commands reject API JSON export options."""
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(
            [
                command,
                "--output-file",
                "/tmp/cache.json",
            ]
        )

    assert captured.value.code == 2
