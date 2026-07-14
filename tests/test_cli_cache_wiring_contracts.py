"""Tests for cache wiring contracts."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pipeline_dashboard_api_client.cli.cache_wiring import (
    CacheWiringResult,
    ManagedClient,
)


@dataclass
class DummyClient:
    """Minimal client satisfying the managed dashboard client protocol."""

    def __init__(self) -> None:
        self.closed = False

    @property
    def is_closed(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True

    def get_dashboard(self) -> bytes:
        return b'{"status":"ok","panels":[]}'

    def get_summary(self) -> bytes:
        return b'{"status":"ok"}'

    def get_health(self) -> bytes:
        return b'{"status":"healthy"}'


@dataclass(frozen=True)
class DummyStore:
    """Minimal cache store used by contract tests."""

    name: str


def test_managed_client_protocol_accepts_compatible_client() -> None:
    """Structural lifecycle-compatible clients satisfy the protocol."""
    client = DummyClient()

    assert isinstance(client, ManagedClient)


def test_managed_client_close_updates_lifecycle_state() -> None:
    """Managed clients expose observable close state."""
    client = DummyClient()

    client.close()

    assert client.is_closed is True


def test_cache_enabled_result_requires_store() -> None:
    """Cache-enabled wiring includes a cache store."""
    client = DummyClient()
    store = DummyStore(name="filesystem")

    result = CacheWiringResult(
        client=client,
        cache_store=store,
        cache_enabled=True,
    )

    assert result.client is client
    assert result.cache_store is store
    assert result.cache_enabled is True
    assert result.uses_cache is True


def test_cache_disabled_result_has_no_store() -> None:
    """Plain client wiring does not expose a cache store."""
    client = DummyClient()

    result = CacheWiringResult[
        DummyClient,
        DummyStore,
    ](
        client=client,
        cache_store=None,
        cache_enabled=False,
    )

    assert result.client is client
    assert result.cache_store is None
    assert result.cache_enabled is False
    assert result.uses_cache is False


def test_cache_enabled_result_rejects_missing_store() -> None:
    """Enabled cache without storage is an invalid composition."""
    with pytest.raises(
        ValueError,
        match="requires a cache store",
    ):
        CacheWiringResult[
            DummyClient,
            DummyStore,
        ](
            client=DummyClient(),
            cache_store=None,
            cache_enabled=True,
        )


def test_cache_disabled_result_rejects_attached_store() -> None:
    """Disabled cache cannot accidentally retain cache storage."""
    with pytest.raises(
        ValueError,
        match="cannot expose a cache store",
    ):
        CacheWiringResult(
            client=DummyClient(),
            cache_store=DummyStore(name="unexpected"),
            cache_enabled=False,
        )
