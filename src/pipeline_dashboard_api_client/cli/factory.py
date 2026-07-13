"""Dependency factory for Pipeline Dashboard API Client CLI."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Self

from pipeline_dashboard_api_client.client import DashboardClient
from pipeline_dashboard_api_client.cli.config import CliRuntimeConfig
from pipeline_dashboard_api_client.parser import ResponseParser
from pipeline_dashboard_api_client.transport import HttpTransport


@dataclass(slots=True)
class CliDependencies:
    """Runtime dependencies required by CLI command handlers."""

    client: DashboardClient
    response_parser: ResponseParser
    transport: HttpTransport
    _closed: bool = False

    @property
    def is_closed(self) -> bool:
        """Return whether dependency resources have been closed."""
        return self._closed

    def close(self) -> None:
        """Close all resources owned by the dependency bundle."""
        if self._closed:
            return

        self.client.close()
        self.transport.close()
        self._closed = True

    def __enter__(self) -> Self:
        """Enter the synchronous dependency context."""
        if self._closed:
            raise RuntimeError("CLI dependencies are closed")

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the synchronous dependency context."""
        self.close()


def build_dependencies(
    config: CliRuntimeConfig,
) -> CliDependencies:
    """Build the default production dependency graph."""
    transport = HttpTransport(config.client)

    client = DashboardClient(
        config.client,
        transport=transport,
    )

    return CliDependencies(
        client=client,
        response_parser=ResponseParser(),
        transport=transport,
    )
