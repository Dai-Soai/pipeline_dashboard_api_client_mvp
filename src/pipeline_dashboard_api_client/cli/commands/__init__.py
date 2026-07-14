"""Command handlers for Pipeline Dashboard API Client CLI."""

from pipeline_dashboard_api_client.cli.commands.cache import (
    CacheCommandStore,
    run_cache_clear_command,
    run_cache_status_command,
)
from pipeline_dashboard_api_client.cli.commands.dashboard import (
    DashboardCommandDependencies,
    run_dashboard_command,
)
from pipeline_dashboard_api_client.cli.commands.health import (
    HealthCommandDependencies,
    run_health_command,
)
from pipeline_dashboard_api_client.cli.commands.summary import (
    SummaryCommandDependencies,
    run_summary_command,
)
from pipeline_dashboard_api_client.cli.commands.validate import (
    ValidateCommandDependencies,
    run_validate_command,
)

__all__ = [
    "CacheCommandStore",
    "DashboardCommandDependencies",
    "HealthCommandDependencies",
    "SummaryCommandDependencies",
    "ValidateCommandDependencies",
    "run_cache_clear_command",
    "run_cache_status_command",
    "run_dashboard_command",
    "run_health_command",
    "run_summary_command",
    "run_validate_command",
]
