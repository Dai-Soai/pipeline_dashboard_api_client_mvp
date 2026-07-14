"""Tests for filesystem cache storage."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline_dashboard_api_client.cache_contracts import (
    CacheEntry,
    CacheKey,
)
from pipeline_dashboard_api_client.cache_store import (
    CacheStoreError,
    FileCacheStore,
)


def build_key(
    resource: str = "dashboard",
) -> CacheKey:
    """Build a reusable cache key."""
    return CacheKey(
        namespace="radar-dashboard",
        resource=resource,
        variant="default",
    )


def build_entry(
    resource: str = "dashboard",
) -> CacheEntry:
    """Build a reusable cache entry."""
    return CacheEntry(
        key=build_key(resource),
        content=b'{"status":"healthy"}',
        stored_at=datetime(
            2026,
            7,
            14,
            20,
            0,
            tzinfo=UTC,
        ),
        status_code=200,
        headers={
            "Content-Type": "application/json",
            "X-Request-ID": "request-cache-31",
        },
        request_id="request-cache-31",
        metadata={
            "source": "network",
            "attempts": 1,
            "validated": True,
        },
    )


def test_store_accepts_string_root(
    tmp_path: Path,
) -> None:
    """Cache root accepts path-like strings."""
    store = FileCacheStore(str(tmp_path))

    assert store.root == tmp_path


def test_store_rejects_existing_file_root(
    tmp_path: Path,
) -> None:
    """An existing regular file cannot be used as cache root."""
    root = tmp_path / "cache"
    root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="directory",
    ):
        FileCacheStore(root)


def test_path_for_uses_cache_key_digest(
    tmp_path: Path,
) -> None:
    """Cache file names are stable SHA256 digests."""
    store = FileCacheStore(tmp_path)
    key = build_key()

    assert store.path_for(key) == (
        tmp_path / f"{key.digest}.json"
    )


def test_write_creates_cache_root(
    tmp_path: Path,
) -> None:
    """Writing creates missing parent directories."""
    root = tmp_path / "nested" / "cache"
    store = FileCacheStore(root)

    written = store.write(build_entry())

    assert root.is_dir()
    assert written.is_file()


def test_write_and_read_round_trip(
    tmp_path: Path,
) -> None:
    """Cache entries survive a filesystem round trip."""
    store = FileCacheStore(tmp_path)
    entry = build_entry()

    store.write(entry)
    loaded = store.read(entry.key)

    assert loaded == entry


def test_binary_content_round_trip(
    tmp_path: Path,
) -> None:
    """Arbitrary binary response content survives Base64 storage."""
    store = FileCacheStore(tmp_path)
    entry = CacheEntry(
        key=build_key(),
        content=b"\x00\xff\x01RADAR",
        stored_at=datetime.now(UTC),
    )

    store.write(entry)
    loaded = store.read(entry.key)

    assert loaded is not None
    assert loaded.content == b"\x00\xff\x01RADAR"


def test_read_missing_entry_returns_none(
    tmp_path: Path,
) -> None:
    """Missing cache files are represented by None."""
    store = FileCacheStore(tmp_path)

    assert store.read(build_key()) is None


def test_write_overwrites_existing_entry(
    tmp_path: Path,
) -> None:
    """Writing the same key replaces the previous value."""
    store = FileCacheStore(tmp_path)
    first = build_entry()
    second = CacheEntry(
        key=first.key,
        content=b'{"status":"warning"}',
        stored_at=datetime.now(UTC),
        status_code=200,
    )

    first_path = store.write(first)
    second_path = store.write(second)
    loaded = store.read(first.key)

    assert first_path == second_path
    assert loaded == second


def test_write_leaves_no_temporary_file(
    tmp_path: Path,
) -> None:
    """Successful atomic writes remove temporary artifacts."""
    store = FileCacheStore(tmp_path)

    store.write(build_entry())

    assert list(tmp_path.glob("*.tmp")) == []


def test_delete_existing_entry(
    tmp_path: Path,
) -> None:
    """Deleting an existing cache file returns true."""
    store = FileCacheStore(tmp_path)
    entry = build_entry()
    store.write(entry)

    deleted = store.delete(entry.key)

    assert deleted is True
    assert store.read(entry.key) is None


def test_delete_missing_entry(
    tmp_path: Path,
) -> None:
    """Deleting a missing cache file returns false."""
    store = FileCacheStore(tmp_path)

    assert store.delete(build_key()) is False


def test_list_paths_is_sorted(
    tmp_path: Path,
) -> None:
    """Managed cache files are listed deterministically."""
    store = FileCacheStore(tmp_path)
    dashboard = build_entry("dashboard")
    summary = build_entry("summary")

    store.write(summary)
    store.write(dashboard)

    paths = store.list_paths()

    assert paths == sorted(paths)
    assert len(paths) == 2
    assert all(path.suffix == ".json" for path in paths)


def test_list_paths_ignores_unmanaged_files(
    tmp_path: Path,
) -> None:
    """Non-JSON files are not treated as cache entries."""
    store = FileCacheStore(tmp_path)
    store.write(build_entry())
    (tmp_path / "notes.txt").write_text(
        "ignore",
        encoding="utf-8",
    )

    assert len(store.list_paths()) == 1


def test_clear_deletes_all_managed_entries(
    tmp_path: Path,
) -> None:
    """Clear removes all JSON cache files."""
    store = FileCacheStore(tmp_path)
    store.write(build_entry("dashboard"))
    store.write(build_entry("summary"))
    (tmp_path / "keep.txt").write_text(
        "preserve",
        encoding="utf-8",
    )

    deleted = store.clear()

    assert deleted == 2
    assert store.list_paths() == []
    assert (tmp_path / "keep.txt").is_file()


def test_clear_missing_root_returns_zero(
    tmp_path: Path,
) -> None:
    """Clearing a missing cache directory is a no-op."""
    store = FileCacheStore(tmp_path / "missing")

    assert store.clear() == 0


def test_read_rejects_invalid_json(
    tmp_path: Path,
) -> None:
    """Malformed cache JSON becomes a normalized store error."""
    store = FileCacheStore(tmp_path)
    path = store.path_for(build_key())
    path.write_text(
        '{"format_version":',
        encoding="utf-8",
    )

    with pytest.raises(
        CacheStoreError,
        match="not valid JSON",
    ):
        store.read(build_key())


def test_read_rejects_non_object_root(
    tmp_path: Path,
) -> None:
    """Cache documents require a JSON object root."""
    store = FileCacheStore(tmp_path)
    path = store.path_for(build_key())
    path.write_text(
        "[]",
        encoding="utf-8",
    )

    with pytest.raises(
        CacheStoreError,
        match="JSON object",
    ):
        store.read(build_key())


def test_read_rejects_unsupported_format(
    tmp_path: Path,
) -> None:
    """Unknown cache format versions are rejected."""
    store = FileCacheStore(tmp_path)
    entry = build_entry()
    path = store.write(entry)
    content = path.read_text(encoding="utf-8").replace(
        '"format_version": 1',
        '"format_version": 99',
    )
    path.write_text(content, encoding="utf-8")

    with pytest.raises(
        CacheStoreError,
        match="unsupported cache format",
    ):
        store.read(entry.key)


def test_read_rejects_invalid_base64(
    tmp_path: Path,
) -> None:
    """Invalid cached response content is rejected."""
    store = FileCacheStore(tmp_path)
    entry = build_entry()
    path = store.write(entry)
    content = path.read_text(encoding="utf-8").replace(
        "eyJzdGF0dXMiOiJoZWFsdGh5In0=",
        "not-valid-base64!",
    )
    path.write_text(content, encoding="utf-8")

    with pytest.raises(
        CacheStoreError,
        match="Base64",
    ):
        store.read(entry.key)


def test_read_rejects_key_mismatch(
    tmp_path: Path,
) -> None:
    """File contents must match the requested cache key."""
    store = FileCacheStore(tmp_path)
    dashboard = build_entry("dashboard")
    summary = build_entry("summary")

    dashboard_path = store.write(dashboard)
    summary_path = store.write(summary)

    dashboard_path.write_text(
        summary_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(
        CacheStoreError,
        match="key mismatch",
    ):
        store.read(dashboard.key)
