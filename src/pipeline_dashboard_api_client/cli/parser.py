"""Argument parser for the Pipeline Dashboard API Client CLI."""

from __future__ import annotations

import argparse


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
    )

    subparsers.add_parser(
        "version",
        help="Display the installed client version.",
    )

    return parser
