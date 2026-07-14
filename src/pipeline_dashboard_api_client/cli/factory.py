"""Dependency factory for Pipeline Dashboard API Client CLI."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Self

from pipeline_dashboard_api_client.cli.cache_factory import (
    build_cache_wiring,
)
from pipeline_dashboard_api_client.cli.config import CliRuntimeConfig
from pipeline_dashboard_api_client.cli.protocols import ManagedClient
from pipeline_dashboard_api_client.client import DashboardClient
from pipeline_dashboard_api_client.parser import ResponseParser
from pipeline_dashboard_api_client.transport import HttpTransport


@dataclass(slots=True)
class CliDependencies:
    """Runtime dependencies required by CLI command handlers."""

    client: ManagedClient
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
    """Build the production dependency graph with optional cache wiring."""
    transport = HttpTransport(config.client)

    network_client = DashboardClient(
        config.client,
        transport=transport,
    )

    cache_wiring = build_cache_wiring(
        config,
        network_client,
    )

    return CliDependencies(
        client=cache_wiring.client,
        response_parser=ResponseParser(),
        transport=transport,
    )
