"""Command handlers for Pipeline Dashboard API Client CLI."""

from pipeline_dashboard_api_client.cli.commands.dashboard import (
    DashboardCommandDependencies,
    run_dashboard_command,
)

__all__ = [
    "DashboardCommandDependencies",
    "run_dashboard_command",
]
