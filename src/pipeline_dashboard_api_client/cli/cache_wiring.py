"""Contracts for composing cache-aware CLI dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pipeline_dashboard_api_client.cli.config import CliRuntimeConfig
from pipeline_dashboard_api_client.cli.protocols import ManagedClient

ClientT = TypeVar("ClientT")
StoreT = TypeVar("StoreT")

__all__ = [
    "CacheWiringBuilder",
    "CacheWiringResult",
    "ManagedClient",
]


@dataclass(frozen=True, slots=True)
class CacheWiringResult(Generic[ClientT, StoreT]):
    """Result produced by cache-aware dependency composition."""

    client: ClientT
    cache_store: StoreT | None
    cache_enabled: bool

    def __post_init__(self) -> None:
        """Reject internally inconsistent wiring results."""
        if self.cache_enabled and self.cache_store is None:
            raise ValueError("cache-enabled wiring requires a cache store")

        if not self.cache_enabled and self.cache_store is not None:
            raise ValueError("cache-disabled wiring cannot expose a cache store")

    @property
    def uses_cache(self) -> bool:
        """Return whether the result contains active cache wiring."""
        return self.cache_enabled


class CacheWiringBuilder(
    Protocol[ClientT, StoreT],
):
    """Callable contract for future cache dependency composition."""

    def __call__(
        self,
        runtime_config: CliRuntimeConfig,
        /,
    ) -> CacheWiringResult[ClientT, StoreT]:
        """Build a cache-aware client composition."""
        ...
