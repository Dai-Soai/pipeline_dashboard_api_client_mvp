"""Health command handler."""

from __future__ import annotations

from typing import Protocol, TextIO

from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.printer import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    print_error,
    print_json,
)
from pipeline_dashboard_api_client.cli.protocols import DashboardCommandClient
from pipeline_dashboard_api_client.contracts import DashboardApiClientError
from pipeline_dashboard_api_client.parser import ResponseParser


class HealthCommandDependencies(Protocol):
    """Dependencies required by the health command."""

    @property
    def client(self) -> DashboardCommandClient:
        """Return the dashboard command client."""
        ...
    response_parser: ResponseParser


def run_health_command(
    dependencies: HealthCommandDependencies,
    *,
    output_mode: OutputMode,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    """Fetch, parse, and print the dashboard backend health document."""
    try:
        raw_response = dependencies.client.get_health()
        parsed_response = dependencies.response_parser.parse_health(
            raw_response
        )
    except DashboardApiClientError as error:
        print_error(
            error,
            output_mode=output_mode,
            stream=error_stream,
        )
        return EXIT_FAILURE

    print_json(
        parsed_response.data.payload,
        output_mode=output_mode,
        stream=output_stream,
    )

    return EXIT_SUCCESS
