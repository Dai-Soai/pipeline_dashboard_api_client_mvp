"""Dashboard backend validation command handler."""

from __future__ import annotations

from typing import Protocol, TextIO

from pipeline_dashboard_api_client.client import DashboardClient
from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.printer import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    print_error,
    print_message,
)
from pipeline_dashboard_api_client.contracts import DashboardApiClientError
from pipeline_dashboard_api_client.parser import ResponseParser

_REACHABLE_MESSAGE = "Dashboard backend reachable."
_UNHEALTHY_MESSAGE = "Dashboard backend returned an unhealthy status."


class ValidateCommandDependencies(Protocol):
    """Dependencies required by the validation command."""

    client: DashboardClient
    response_parser: ResponseParser


def run_validate_command(
    dependencies: ValidateCommandDependencies,
    *,
    output_mode: OutputMode,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    """Validate connectivity and health status of the dashboard backend."""
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

    normalized_status = parsed_response.data.status.casefold()

    if normalized_status not in {"healthy", "ok"}:
        print_message(
            _UNHEALTHY_MESSAGE,
            stream=error_stream,
        )
        return EXIT_FAILURE

    print_message(
        _REACHABLE_MESSAGE,
        stream=output_stream,
    )
    return EXIT_SUCCESS
