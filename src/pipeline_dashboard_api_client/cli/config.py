"""CLI configuration builder for Pipeline Dashboard API Client."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum

from pipeline_dashboard_api_client.contracts import (
    ApiClientConfig,
    Headers,
)


class OutputMode(StrEnum):
    """Supported CLI JSON output modes."""

    PRETTY = "pretty"
    COMPACT = "compact"


class CliConfigError(ValueError):
    """Raised when CLI arguments cannot produce a valid configuration."""


@dataclass(frozen=True, slots=True)
class CliRuntimeConfig:
    """Normalized runtime configuration produced from CLI arguments."""

    client: ApiClientConfig
    output_mode: OutputMode


def build_cli_config(
    args: argparse.Namespace,
) -> CliRuntimeConfig:
    """Build normalized runtime configuration from parsed CLI arguments."""
    base_url = _required_string_argument(args, "base_url")
    timeout_seconds = _required_float_argument(args, "timeout")
    max_retries = _required_int_argument(args, "retry")
    output_mode = _parse_output_mode(
        _required_string_argument(args, "output_mode")
    )
    headers = parse_headers(
        _optional_string_list_argument(args, "header")
    )

    try:
        client_config = ApiClientConfig(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            default_headers=headers,
        )
    except ValueError as exc:
        raise CliConfigError(str(exc)) from exc

    return CliRuntimeConfig(
        client=client_config,
        output_mode=output_mode,
    )


def parse_headers(
    raw_headers: list[str] | None,
) -> Headers:
    """Parse repeated NAME=VALUE CLI header declarations."""
    if raw_headers is None:
        return {}

    parsed_headers: Headers = {}

    for declaration in raw_headers:
        name, separator, value = declaration.partition("=")

        if not separator:
            raise CliConfigError(
                "header must use NAME=VALUE format: "
                f"{declaration!r}"
            )

        normalized_name = name.strip()
        normalized_value = value.strip()

        if not normalized_name:
            raise CliConfigError(
                "header name must not be empty"
            )

        if not normalized_value:
            raise CliConfigError(
                f"header value must not be empty: {normalized_name}"
            )

        existing_name = _find_header_name(
            parsed_headers,
            normalized_name,
        )

        if existing_name is not None:
            del parsed_headers[existing_name]

        parsed_headers[normalized_name] = normalized_value

    return parsed_headers


def _find_header_name(
    headers: Headers,
    candidate: str,
) -> str | None:
    """Find an existing case-insensitive HTTP header name."""
    normalized_candidate = candidate.casefold()

    for existing_name in headers:
        if existing_name.casefold() == normalized_candidate:
            return existing_name

    return None


def _parse_output_mode(value: str) -> OutputMode:
    """Convert a parsed string into a supported output mode."""
    try:
        return OutputMode(value)
    except ValueError as exc:
        raise CliConfigError(
            f"unsupported output mode: {value!r}"
        ) from exc


def _required_string_argument(
    args: argparse.Namespace,
    name: str,
) -> str:
    """Read a required non-empty string argument."""
    value = getattr(args, name, None)

    if not isinstance(value, str) or not value.strip():
        raise CliConfigError(
            f"missing or invalid CLI argument: {name}"
        )

    return value.strip()


def _required_float_argument(
    args: argparse.Namespace,
    name: str,
) -> float:
    """Read a required floating-point argument."""
    value = getattr(args, name, None)

    if isinstance(value, bool) or not isinstance(
        value,
        int | float,
    ):
        raise CliConfigError(
            f"missing or invalid CLI argument: {name}"
        )

    return float(value)


def _required_int_argument(
    args: argparse.Namespace,
    name: str,
) -> int:
    """Read a required integer argument."""
    value = getattr(args, name, None)

    if isinstance(value, bool) or not isinstance(value, int):
        raise CliConfigError(
            f"missing or invalid CLI argument: {name}"
        )

    return value


def _optional_string_list_argument(
    args: argparse.Namespace,
    name: str,
) -> list[str] | None:
    """Read an optional list of string arguments."""
    value = getattr(args, name, None)

    if value is None:
        return None

    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise CliConfigError(
            f"invalid CLI argument: {name}"
        )

    return list(value)
