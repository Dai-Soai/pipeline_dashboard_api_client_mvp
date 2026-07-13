"""CLI package for Pipeline Dashboard API Client."""

from pipeline_dashboard_api_client.cli.main import main
from pipeline_dashboard_api_client.cli.parser import build_parser

__all__ = [
    "build_parser",
    "main",
]
