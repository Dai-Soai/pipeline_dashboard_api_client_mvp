"""Atomic filesystem implementation of the JSON exporter contract."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from pathlib import Path

from pipeline_dashboard_api_client.cli.export_contracts import (
    JsonExportError,
    JsonExportErrorKind,
    JsonExportRequest,
    JsonExportResult,
)
from pipeline_dashboard_api_client.cli.printer import render_json
from pipeline_dashboard_api_client.parser import JsonValue


class AtomicJsonFileExporter:
    """Export normalized JSON values through atomic filesystem writes."""

    def export(
        self,
        value: JsonValue,
        request: JsonExportRequest,
    ) -> JsonExportResult:
        """Serialize and atomically persist one JSON-compatible value."""
        destination = request.path
        overwritten = self._inspect_destination(
            destination,
            overwrite=request.overwrite,
        )

        self._ensure_parent_directory(destination)

        content = (
            render_json(
                value,
                output_mode=request.output_mode,
            )
            + "\n"
        )
        encoded_content = content.encode("utf-8")

        temporary_path = self._write_temporary_file(
            destination,
            encoded_content,
        )

        try:
            self._publish_temporary_file(
                temporary_path,
                destination,
                overwrite=request.overwrite,
            )
        finally:
            self._remove_temporary_file(
                temporary_path,
            )

        return JsonExportResult(
            path=destination,
            bytes_written=len(encoded_content),
            overwritten=overwritten,
        )

    @staticmethod
    def _inspect_destination(
        destination: Path,
        *,
        overwrite: bool,
    ) -> bool:
        """Validate the destination and report whether it exists."""
        if not destination.exists():
            return False

        if destination.is_dir():
            raise JsonExportError(
                kind=JsonExportErrorKind.INVALID_PATH,
                path=destination,
                message=(
                    "JSON export destination must not be a directory"
                ),
            )

        if not overwrite:
            raise JsonExportError(
                kind=JsonExportErrorKind.INVALID_PATH,
                path=destination,
                message=(
                    "JSON export destination already exists and "
                    "overwrite is disabled"
                ),
            )

        return True

    @staticmethod
    def _ensure_parent_directory(
        destination: Path,
    ) -> None:
        """Create the destination parent directory when necessary."""
        parent = destination.parent

        try:
            parent.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise JsonExportError(
                kind=JsonExportErrorKind.PARENT_CREATION_FAILED,
                path=destination,
                message=(
                    "failed to create JSON export parent directory: "
                    f"{exc}"
                ),
            ) from exc

        if not parent.is_dir():
            raise JsonExportError(
                kind=JsonExportErrorKind.PARENT_CREATION_FAILED,
                path=destination,
                message=(
                    "JSON export parent path is not a directory"
                ),
            )

    @staticmethod
    def _write_temporary_file(
        destination: Path,
        content: bytes,
    ) -> Path:
        """Write and synchronize a temporary file beside the destination."""
        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(
                    missing_ok=True,
                )

            raise JsonExportError(
                kind=JsonExportErrorKind.WRITE_FAILED,
                path=destination,
                message=(
                    "failed to write temporary JSON export file: "
                    f"{exc}"
                ),
            ) from exc

        if temporary_path is None:
            raise AssertionError(
                "temporary JSON export path was not created"
            )

        return temporary_path

    @staticmethod
    def _publish_temporary_file(
        temporary_path: Path,
        destination: Path,
        *,
        overwrite: bool,
    ) -> None:
        """Publish a temporary file atomically."""
        try:
            if overwrite:
                os.replace(
                    temporary_path,
                    destination,
                )
                return

            os.link(
                temporary_path,
                destination,
            )
        except FileExistsError as exc:
            raise JsonExportError(
                kind=JsonExportErrorKind.INVALID_PATH,
                path=destination,
                message=(
                    "JSON export destination already exists and "
                    "overwrite is disabled"
                ),
            ) from exc
        except OSError as exc:
            raise JsonExportError(
                kind=JsonExportErrorKind.REPLACE_FAILED,
                path=destination,
                message=(
                    "failed to publish temporary JSON export file: "
                    f"{exc}"
                ),
            ) from exc

    @staticmethod
    def _remove_temporary_file(
        temporary_path: Path,
    ) -> None:
        """Remove a temporary file that remains after publication."""
        with suppress(OSError):
            temporary_path.unlink(
                missing_ok=True,
            )
