"""Command-line interface for Pipeline Dashboard API Client."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from pipeline_dashboard_api_client.version import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build and return the command-line argument parser."""
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
    )

    subparsers.add_parser(
        "version",
        help="Display the installed client version.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
