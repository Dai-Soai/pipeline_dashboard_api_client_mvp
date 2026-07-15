"""Main dispatcher for the Pipeline Dashboard API Client CLI."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from pipeline_dashboard_api_client.cache_store import FileCacheStore
from pipeline_dashboard_api_client.cli.commands import (
    run_cache_clear_command,
    run_cache_status_command,
    run_dashboard_command,
    run_health_command,
    run_summary_command,
    run_validate_command,
)
from pipeline_dashboard_api_client.cli.config import (
    CliConfigError,
    CliRuntimeConfig,
    OutputMode,
    build_cli_config,
)
from pipeline_dashboard_api_client.cli.factory import (
    CliDependencies,
    build_dependencies,
)
from pipeline_dashboard_api_client.cli.parser import build_parser
from pipeline_dashboard_api_client.cli.printer import (
    EXIT_USAGE_ERROR,
    print_message,
)
from pipeline_dashboard_api_client.version import __version__

DependencyBuilder = Callable[[CliRuntimeConfig], CliDependencies]


def main(
    argv: Sequence[str] | None = None,
    *,
    dependency_builder: DependencyBuilder = build_dependencies,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    """Parse arguments, build dependencies, and dispatch a CLI command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    command = _read_command(args)

    if command == "version":
        print_message(
            __version__,
            stream=output_stream,
        )
        return 0

    if command in {
        "cache-status",
        "cache-clear",
    }:
        return dispatch_cache_command(
            command,
            args,
            output_stream=output_stream,
        )

    try:
        runtime_config = build_cli_config(args)
    except CliConfigError as error:
        print_message(
            f"Configuration error: {error}",
            stream=error_stream,
        )
        return EXIT_USAGE_ERROR

    with dependency_builder(runtime_config) as dependencies:
        return dispatch_command(
            command,
            dependencies,
            runtime_config=runtime_config,
            output_stream=output_stream,
            error_stream=error_stream,
        )


def dispatch_cache_command(
    command: str,
    args: argparse.Namespace,
    *,
    output_stream: TextIO | None = None,
) -> int:
    """Dispatch a filesystem cache management command."""
    cache_dir = getattr(args, "cache_dir", None)
    output_mode_value = getattr(
        args,
        "output_mode",
        OutputMode.PRETTY.value,
    )

    if not isinstance(cache_dir, str) or not cache_dir.strip():
        raise RuntimeError(
            "parsed cache directory is missing"
        )

    if not isinstance(output_mode_value, str):
        raise RuntimeError(
            "parsed cache output mode is invalid"
        )

    try:
        output_mode = OutputMode(output_mode_value)
    except ValueError as exc:
        raise RuntimeError(
            "parsed cache output mode is invalid"
        ) from exc

    store = FileCacheStore(
        Path(cache_dir).expanduser(),
    )

    if command == "cache-status":
        return run_cache_status_command(
            store,
            output_mode=output_mode,
            output_stream=output_stream,
        )

    if command == "cache-clear":
        return run_cache_clear_command(
            store,
            output_mode=output_mode,
            output_stream=output_stream,
        )

    raise RuntimeError(
        f"unsupported cache command: {command}"
    )


def dispatch_command(
    command: str,
    dependencies: CliDependencies,
    *,
    runtime_config: CliRuntimeConfig,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    """Dispatch a normalized command to its dedicated handler."""
    if command == "dashboard":
        return run_dashboard_command(
            dependencies,
            output_mode=runtime_config.output_mode,
            output_stream=output_stream,
            error_stream=error_stream,
        )

    if command == "summary":
        return run_summary_command(
            dependencies,
            output_mode=runtime_config.output_mode,
            output_stream=output_stream,
            error_stream=error_stream,
        )

    if command == "health":
        return run_health_command(
            dependencies,
            output_mode=runtime_config.output_mode,
            output_stream=output_stream,
            error_stream=error_stream,
        )

    if command == "validate":
        return run_validate_command(
            dependencies,
            output_mode=runtime_config.output_mode,
            output_stream=output_stream,
            error_stream=error_stream,
        )

    raise RuntimeError(
        f"unsupported dispatched command: {command}"
    )


def _read_command(
    args: argparse.Namespace,
) -> str:
    """Read and validate the command stored by argparse."""
    command = getattr(args, "command", None)

    if not isinstance(command, str) or not command:
        raise RuntimeError("parsed CLI command is missing")

    return command


if __name__ == "__main__":
    raise SystemExit(main())
