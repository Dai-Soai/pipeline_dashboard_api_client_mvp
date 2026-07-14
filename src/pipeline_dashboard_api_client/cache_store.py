"""Filesystem cache store for Pipeline Dashboard API Client."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Final, TypeAlias, cast

from pipeline_dashboard_api_client.cache_contracts import (
    CacheEntry,
    CacheKey,
    CacheMetadataValue,
)
from pipeline_dashboard_api_client.contracts import Headers

CacheDocumentValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | list["CacheDocumentValue"]
    | dict[str, "CacheDocumentValue"]
)
CacheDocument: TypeAlias = dict[str, CacheDocumentValue]

_CACHE_FORMAT_VERSION: Final[int] = 1
_CACHE_FILE_SUFFIX: Final[str] = ".json"


class CacheStoreError(RuntimeError):
    """Raised when the filesystem cache store cannot complete an operation."""


class FileCacheStore:
    """Persist raw dashboard responses as atomic JSON cache files."""

    def __init__(
        self,
        root: str | Path,
    ) -> None:
        """Initialize the cache store."""
        normalized_root = Path(root).expanduser()

        if normalized_root.exists() and not normalized_root.is_dir():
            raise ValueError(
                "cache root must be a directory path"
            )

        self._root = normalized_root

    @property
    def root(self) -> Path:
        """Return the configured cache root."""
        return self._root

    def write(
        self,
        entry: CacheEntry,
    ) -> Path:
        """Persist a cache entry using an atomic file replacement."""
        self._ensure_root()

        target = self.path_for(entry.key)
        temporary = target.with_suffix(
            f"{target.suffix}.tmp"
        )
        document = self._serialize_entry(entry)

        try:
            serialized = json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )

            temporary.write_text(
                f"{serialized}\n",
                encoding="utf-8",
            )

            os.replace(
                temporary,
                target,
            )
        except OSError as exc:
            self._remove_temporary_file(temporary)

            raise CacheStoreError(
                f"failed to write cache entry: {target}"
            ) from exc

        return target

    def read(
        self,
        key: CacheKey,
    ) -> CacheEntry | None:
        """Read a cache entry, returning None when it does not exist."""
        path = self.path_for(key)

        if not path.exists():
            return None

        if not path.is_file():
            raise CacheStoreError(
                f"cache path is not a file: {path}"
            )

        try:
            raw_document = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError) as exc:
            raise CacheStoreError(
                f"failed to read cache entry: {path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise CacheStoreError(
                f"cache entry is not valid JSON: {path}"
            ) from exc

        document = self._require_document(
            raw_document,
            path=path,
        )
        entry = self._deserialize_entry(
            document,
            path=path,
        )

        if entry.key != key:
            raise CacheStoreError(
                f"cache key mismatch: {path}"
            )

        return entry

    def delete(
        self,
        key: CacheKey,
    ) -> bool:
        """Delete a cache entry and report whether it existed."""
        path = self.path_for(key)

        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise CacheStoreError(
                f"failed to delete cache entry: {path}"
            ) from exc

        return True

    def clear(self) -> int:
        """Delete all managed cache files and return the deletion count."""
        if not self._root.exists():
            return 0

        if not self._root.is_dir():
            raise CacheStoreError(
                f"cache root is not a directory: {self._root}"
            )

        deleted = 0

        for path in self._root.glob(
            f"*{_CACHE_FILE_SUFFIX}"
        ):
            if not path.is_file():
                continue

            try:
                path.unlink()
            except OSError as exc:
                raise CacheStoreError(
                    f"failed to delete cache entry: {path}"
                ) from exc

            deleted += 1

        return deleted

    def list_paths(self) -> list[Path]:
        """Return all managed cache files in deterministic order."""
        if not self._root.exists():
            return []

        if not self._root.is_dir():
            raise CacheStoreError(
                f"cache root is not a directory: {self._root}"
            )

        return sorted(
            path
            for path in self._root.glob(
                f"*{_CACHE_FILE_SUFFIX}"
            )
            if path.is_file()
        )

    def path_for(
        self,
        key: CacheKey,
    ) -> Path:
        """Return the filesystem path associated with a cache key."""
        return self._root / (
            f"{key.digest}{_CACHE_FILE_SUFFIX}"
        )

    def _ensure_root(self) -> None:
        """Create the cache root when necessary."""
        try:
            self._root.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise CacheStoreError(
                f"failed to create cache root: {self._root}"
            ) from exc

        if not self._root.is_dir():
            raise CacheStoreError(
                f"cache root is not a directory: {self._root}"
            )

    @staticmethod
    def _serialize_entry(
        entry: CacheEntry,
    ) -> CacheDocument:
        """Convert a cache entry into a JSON-compatible document."""
        return {
            "format_version": _CACHE_FORMAT_VERSION,
            "key": {
                "namespace": entry.key.namespace,
                "resource": entry.key.resource,
                "variant": entry.key.variant,
            },
            "content_base64": base64.b64encode(
                entry.content
            ).decode("ascii"),
            "stored_at": entry.stored_at.isoformat(),
            "status_code": entry.status_code,
            "headers": dict(entry.headers),
            "request_id": entry.request_id,
            "metadata": dict(entry.metadata),
        }

    @staticmethod
    def _deserialize_entry(
        document: CacheDocument,
        *,
        path: Path,
    ) -> CacheEntry:
        """Convert a validated cache document into a cache entry."""
        format_version = FileCacheStore._require_int(
            document,
            "format_version",
            path=path,
        )

        if format_version != _CACHE_FORMAT_VERSION:
            raise CacheStoreError(
                "unsupported cache format version "
                f"{format_version}: {path}"
            )

        key_document = FileCacheStore._require_mapping(
            document,
            "key",
            path=path,
        )

        key = CacheKey(
            namespace=FileCacheStore._require_string(
                key_document,
                "namespace",
                path=path,
            ),
            resource=FileCacheStore._require_string(
                key_document,
                "resource",
                path=path,
            ),
            variant=FileCacheStore._require_string(
                key_document,
                "variant",
                path=path,
            ),
        )

        encoded_content = FileCacheStore._require_string(
            document,
            "content_base64",
            path=path,
        )

        try:
            content = base64.b64decode(
                encoded_content,
                validate=True,
            )
        except ValueError as exc:
            raise CacheStoreError(
                f"cache content is not valid Base64: {path}"
            ) from exc

        stored_at_value = FileCacheStore._require_string(
            document,
            "stored_at",
            path=path,
        )

        try:
            stored_at = datetime.fromisoformat(
                stored_at_value
            )
        except ValueError as exc:
            raise CacheStoreError(
                f"cache stored_at is invalid: {path}"
            ) from exc

        headers = FileCacheStore._read_headers(
            document,
            path=path,
        )
        metadata = FileCacheStore._read_metadata(
            document,
            path=path,
        )
        request_id = FileCacheStore._read_optional_string(
            document,
            "request_id",
            path=path,
        )

        try:
            return CacheEntry(
                key=key,
                content=content,
                stored_at=stored_at,
                status_code=FileCacheStore._require_int(
                    document,
                    "status_code",
                    path=path,
                ),
                headers=headers,
                request_id=request_id,
                metadata=metadata,
            )
        except ValueError as exc:
            raise CacheStoreError(
                f"cache entry validation failed: {path}"
            ) from exc

    @staticmethod
    def _require_document(
        value: object,
        *,
        path: Path,
    ) -> CacheDocument:
        """Require a JSON object cache document."""
        if not isinstance(value, dict):
            raise CacheStoreError(
                f"cache root must be a JSON object: {path}"
            )

        return cast(CacheDocument, value)

    @staticmethod
    def _require_mapping(
        document: Mapping[str, CacheDocumentValue],
        key: str,
        *,
        path: Path,
    ) -> Mapping[str, CacheDocumentValue]:
        """Require a mapping field."""
        value = document.get(key)

        if not isinstance(value, dict):
            raise CacheStoreError(
                f"cache field '{key}' must be an object: {path}"
            )

        return value

    @staticmethod
    def _require_string(
        document: Mapping[str, CacheDocumentValue],
        key: str,
        *,
        path: Path,
    ) -> str:
        """Require a non-empty string field."""
        value = document.get(key)

        if not isinstance(value, str) or not value:
            raise CacheStoreError(
                f"cache field '{key}' must be a string: {path}"
            )

        return value

    @staticmethod
    def _require_int(
        document: Mapping[str, CacheDocumentValue],
        key: str,
        *,
        path: Path,
    ) -> int:
        """Require an integer field excluding booleans."""
        value = document.get(key)

        if isinstance(value, bool) or not isinstance(
            value,
            int,
        ):
            raise CacheStoreError(
                f"cache field '{key}' must be an integer: {path}"
            )

        return value

    @staticmethod
    def _read_optional_string(
        document: Mapping[str, CacheDocumentValue],
        key: str,
        *,
        path: Path,
    ) -> str | None:
        """Read a nullable string field."""
        value = document.get(key)

        if value is None:
            return None

        if not isinstance(value, str):
            raise CacheStoreError(
                f"cache field '{key}' must be a string or null: {path}"
            )

        return value

    @staticmethod
    def _read_headers(
        document: Mapping[str, CacheDocumentValue],
        *,
        path: Path,
    ) -> Headers:
        """Read and validate cached response headers."""
        raw_headers = FileCacheStore._require_mapping(
            document,
            "headers",
            path=path,
        )
        headers: Headers = {}

        for name, value in raw_headers.items():
            if not isinstance(value, str):
                raise CacheStoreError(
                    "cache header values must be strings: "
                    f"{path}"
                )

            headers[name] = value

        return headers

    @staticmethod
    def _read_metadata(
        document: Mapping[str, CacheDocumentValue],
        *,
        path: Path,
    ) -> dict[str, CacheMetadataValue]:
        """Read and validate scalar cache metadata."""
        raw_metadata = FileCacheStore._require_mapping(
            document,
            "metadata",
            path=path,
        )
        metadata: dict[str, CacheMetadataValue] = {}

        for name, value in raw_metadata.items():
            if isinstance(value, (dict, list)):
                raise CacheStoreError(
                    "cache metadata values must be scalar: "
                    f"{path}"
                )

            metadata[name] = value

        return metadata

    @staticmethod
    def _remove_temporary_file(
        path: Path,
    ) -> None:
        """Best-effort removal of a failed temporary cache file."""
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            return
