"""Contracts for exporting normalized JSON documents to files."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.parser import JsonValue


class JsonExportErrorKind(StrEnum):
    """Normalized categories for local JSON export failures."""

    INVALID_PATH = "invalid_path"
    PARENT_CREATION_FAILED = "parent_creation_failed"
    WRITE_FAILED = "write_failed"
    REPLACE_FAILED = "replace_failed"


@dataclass(frozen=True, slots=True)
class JsonExportRequest:
    """Configuration for exporting one JSON-compatible value."""

    path: Path
    output_mode: OutputMode = OutputMode.PRETTY
    overwrite: bool = False

    def __post_init__(self) -> None:
        """Normalize the destination path."""
        object.__setattr__(
            self,
            "path",
            self.path.expanduser(),
        )


@dataclass(frozen=True, slots=True)
class JsonExportResult:
    """Outcome of a successful JSON file export."""

    path: Path
    bytes_written: int
    overwritten: bool

    def __post_init__(self) -> None:
        """Normalize and validate export result metadata."""
        if (
            isinstance(self.bytes_written, bool)
            or self.bytes_written < 0
        ):
            raise ValueError(
                "bytes_written must be a non-negative integer"
            )

        object.__setattr__(
            self,
            "path",
            self.path.expanduser(),
        )


class JsonExportError(RuntimeError):
    """Raised when a normalized JSON file export operation fails."""

    def __init__(
        self,
        *,
        kind: JsonExportErrorKind,
        path: Path,
        message: str,
    ) -> None:
        """Initialize a normalized local export failure."""
        normalized_message = message.strip()

        if not normalized_message:
            raise ValueError(
                "export error message must not be empty"
            )

        self.kind = kind
        self.path = path.expanduser()

        super().__init__(normalized_message)


@runtime_checkable
class JsonExporter(Protocol):
    """Exporter capable of persisting normalized JSON values."""

    def export(
        self,
        value: JsonValue,
        request: JsonExportRequest,
    ) -> JsonExportResult:
        """Export one JSON-compatible value."""
        ...
