"""Tests for the modular CLI argument parser."""

import pytest

from pipeline_dashboard_api_client.cli.parser import (
    DEFAULT_BASE_URL,
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
