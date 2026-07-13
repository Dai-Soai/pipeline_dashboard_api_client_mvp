"""Main entry point for the Pipeline Dashboard API Client CLI."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from pipeline_dashboard_api_client.cli.parser import build_parser
from pipeline_dashboard_api_client.version import __version__


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    return _unsupported_command(parser, args.command)


def _unsupported_command(
    parser: argparse.ArgumentParser,
    command: str,
) -> int:
    """Report an unsupported command through argparse."""
    parser.error(f"unsupported command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
