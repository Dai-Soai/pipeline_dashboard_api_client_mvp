"""CLI output rendering and printing utilities."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import TextIO

from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.contracts import (
    DashboardApiClientError,
    JsonScalar,
)
from pipeline_dashboard_api_client.parser import (
    JsonObject,
    JsonValue,
)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE_ERROR = 2


def render_json(
    value: JsonValue,
    *,
    output_mode: OutputMode,
) -> str:
    """Serialize a JSON-compatible value using the selected output mode."""
    if output_mode is OutputMode.PRETTY:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def print_json(
    value: JsonValue,
    *,
    output_mode: OutputMode,
    stream: TextIO | None = None,
) -> None:
    """Print serialized JSON to the selected output stream."""
    target = sys.stdout if stream is None else stream

    print(
        render_json(
            value,
            output_mode=output_mode,
        ),
        file=target,
    )


def print_message(
    message: str,
    *,
    stream: TextIO | None = None,
) -> None:
    """Print a normalized human-readable message."""
    normalized = message.strip()

    if not normalized:
        raise ValueError("message must not be empty")

    target = sys.stdout if stream is None else stream
    print(normalized, file=target)


def build_error_document(
    error: DashboardApiClientError,
) -> JsonObject:
    """Convert a normalized client exception into a JSON document."""
    document: JsonObject = {
        "error": {
            "kind": error.kind.value,
            "message": str(error),
        }
    }

    error_value = document["error"]
    if not isinstance(error_value, dict):
        raise AssertionError("error document must contain an object")

    error_object = error_value

    if error.status_code is not None:
        error_object["status_code"] = error.status_code

    if error.request_id is not None:
        error_object["request_id"] = error.request_id

    if error.payload.details:
        error_object["details"] = _copy_details(
            error.payload.details
        )

    return document


def print_error(
    error: DashboardApiClientError,
    *,
    output_mode: OutputMode,
    stream: TextIO | None = None,
) -> None:
    """Print a normalized client error as JSON to stderr by default."""
    target = sys.stderr if stream is None else stream

    print_json(
        build_error_document(error),
        output_mode=output_mode,
        stream=target,
    )


def _copy_details(
    details: Mapping[str, JsonScalar],
) -> JsonObject:
    """Copy scalar error details into a JSON object."""
    return {
        key: value
        for key, value in details.items()
    }
