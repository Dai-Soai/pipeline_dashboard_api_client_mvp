"""Dashboard backend validation command handler."""

from __future__ import annotations

from typing import Protocol, TextIO

from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.export_contracts import (
    JsonExporter,
    JsonExportError,
    JsonExportRequest,
)
from pipeline_dashboard_api_client.cli.printer import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    print_error,
    print_json,
    print_message,
)
from pipeline_dashboard_api_client.cli.protocols import DashboardCommandClient
from pipeline_dashboard_api_client.contracts import DashboardApiClientError
from pipeline_dashboard_api_client.parser import (
    JsonObject,
    ResponseParser,
)

_REACHABLE_MESSAGE = "Dashboard backend reachable."
_UNHEALTHY_MESSAGE = "Dashboard backend returned an unhealthy status."


class ValidateCommandDependencies(Protocol):
    """Dependencies required by the validation command."""

    @property
    def client(self) -> DashboardCommandClient:
        """Return the dashboard command client."""
        ...

    response_parser: ResponseParser


def run_validate_command(
    dependencies: ValidateCommandDependencies,
    *,
    output_mode: OutputMode,
    export_request: JsonExportRequest | None = None,
    exporter: JsonExporter | None = None,
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

    if export_request is None:
        print_message(
            _REACHABLE_MESSAGE,
            stream=output_stream,
        )
        return EXIT_SUCCESS

    if exporter is None:
        print_json(
            {
                "error": {
                    "kind": "exporter_missing",
                    "message": (
                        "JSON exporter is required when an export "
                        "request is provided"
                    ),
                    "path": str(export_request.path),
                }
            },
            output_mode=output_mode,
            stream=error_stream,
        )
        return EXIT_FAILURE

    validation_result: JsonObject = {
        "message": _REACHABLE_MESSAGE,
        "valid": True,
    }

    try:
        exporter.export(
            validation_result,
            export_request,
        )
    except JsonExportError as error:
        print_json(
            {
                "error": {
                    "kind": error.kind.value,
                    "message": str(error),
                    "path": str(error.path),
                }
            },
            output_mode=output_mode,
            stream=error_stream,
        )
        return EXIT_FAILURE

    return EXIT_SUCCESS
