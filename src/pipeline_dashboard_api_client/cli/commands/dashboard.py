"""Dashboard command handler."""

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
)
from pipeline_dashboard_api_client.cli.protocols import DashboardCommandClient
from pipeline_dashboard_api_client.contracts import (
    DashboardApiClientError,
)
from pipeline_dashboard_api_client.parser import ResponseParser


class DashboardCommandDependencies(Protocol):
    """Dependencies required by the dashboard command."""

    @property
    def client(self) -> DashboardCommandClient:
        """Return the dashboard command client."""
        ...

    response_parser: ResponseParser


def run_dashboard_command(
    dependencies: DashboardCommandDependencies,
    *,
    output_mode: OutputMode,
    export_request: JsonExportRequest | None = None,
    exporter: JsonExporter | None = None,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    """Fetch, parse, and emit the complete dashboard document."""
    try:
        raw_response = dependencies.client.get_dashboard()
        parsed_response = dependencies.response_parser.parse_dashboard(
            raw_response
        )
    except DashboardApiClientError as error:
        print_error(
            error,
            output_mode=output_mode,
            stream=error_stream,
        )
        return EXIT_FAILURE

    payload = parsed_response.data.payload

    if export_request is None:
        print_json(
            payload,
            output_mode=output_mode,
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

    try:
        exporter.export(
            payload,
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
