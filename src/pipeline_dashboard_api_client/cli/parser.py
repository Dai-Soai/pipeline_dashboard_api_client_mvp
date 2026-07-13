"""Argument parser for the Pipeline Dashboard API Client CLI."""

from __future__ import annotations

import argparse

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_OUTPUT_MODE = "pretty"


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="radar-dashboard-client",
        description=(
            "Typed API client for the RADAR_SERVICE "
            "Pipeline Dashboard Backend."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="COMMAND",
    )

    subparsers.add_parser(
        "version",
        help="Display the installed client version.",
        description="Display the installed client version.",
    )

    _add_api_command(
        subparsers,
        name="dashboard",
        help_text="Fetch the complete dashboard document.",
    )
    _add_api_command(
        subparsers,
        name="summary",
        help_text="Fetch the dashboard summary document.",
    )
    _add_api_command(
        subparsers,
        name="health",
        help_text="Fetch the dashboard backend health document.",
    )
    _add_api_command(
        subparsers,
        name="validate",
        help_text="Validate connectivity with the dashboard backend.",
    )

    return parser


def _add_api_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    name: str,
    help_text: str,
) -> argparse.ArgumentParser:
    """Create an API command parser with shared client options."""
    command_parser = subparsers.add_parser(
        name,
        help=help_text,
        description=help_text,
    )

    _add_common_api_options(command_parser)
    return command_parser


def _add_common_api_options(
    parser: argparse.ArgumentParser,
) -> None:
    """Add options shared by dashboard API commands."""
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        metavar="URL",
        help=(
            "Dashboard backend base URL "
            f"(default: {DEFAULT_BASE_URL})."
        ),
    )

    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help=(
            "Request timeout in seconds "
            f"(default: {DEFAULT_TIMEOUT_SECONDS:g})."
        ),
    )

    parser.add_argument(
        "--retry",
        type=_non_negative_int,
        default=DEFAULT_MAX_RETRIES,
        metavar="COUNT",
        help=(
            "Maximum retry count "
            f"(default: {DEFAULT_MAX_RETRIES})."
        ),
    )

    parser.add_argument(
        "--header",
        action="append",
        default=None,
        metavar="NAME=VALUE",
        help=(
            "Add an HTTP header. May be supplied more than once."
        ),
    )

    output_group = parser.add_mutually_exclusive_group()

    output_group.add_argument(
        "--pretty",
        dest="output_mode",
        action="store_const",
        const="pretty",
        help="Print indented JSON output.",
    )

    output_group.add_argument(
        "--compact",
        dest="output_mode",
        action="store_const",
        const="compact",
        help="Print compact JSON output.",
    )

    parser.set_defaults(output_mode=DEFAULT_OUTPUT_MODE)


def _positive_float(value: str) -> float:
    """Parse a strictly positive floating-point value."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected a number, received: {value!r}"
        ) from exc

    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            "value must be greater than zero"
        )

    return parsed


def _non_negative_int(value: str) -> int:
    """Parse a non-negative integer value."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected an integer, received: {value!r}"
        ) from exc

    if parsed < 0:
        raise argparse.ArgumentTypeError(
            "value must not be negative"
        )

    return parsed
