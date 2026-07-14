"""Typed cache contracts for Pipeline Dashboard API Client."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import TypeAlias

from pipeline_dashboard_api_client.contracts import Headers

CacheMetadataValue: TypeAlias = str | int | float | bool | None


class CacheStatus(StrEnum):
    """Normalized cache freshness states."""

    FRESH = "fresh"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """Cache behavior and expiration policy."""

    ttl_seconds: float = 300.0
    allow_stale: bool = False

    def __post_init__(self) -> None:
        """Validate cache policy values."""
        if self.ttl_seconds <= 0:
            raise ValueError(
                "ttl_seconds must be greater than zero"
            )


@dataclass(frozen=True, slots=True)
class CacheKey:
    """Stable cache key for a dashboard API resource."""

    namespace: str
    resource: str
    variant: str = "default"

    def __post_init__(self) -> None:
        """Validate and normalize cache key parts."""
        namespace = self.namespace.strip()
        resource = self.resource.strip().strip("/")
        variant = self.variant.strip()

        if not namespace:
            raise ValueError("namespace must not be empty")

        if not resource:
            raise ValueError("resource must not be empty")

        if not variant:
            raise ValueError("variant must not be empty")

        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "resource", resource)
        object.__setattr__(self, "variant", variant)

    @property
    def canonical(self) -> str:
        """Return the canonical cache key string."""
        return (
            f"{self.namespace}:"
            f"{self.resource}:"
            f"{self.variant}"
        )

    @property
    def digest(self) -> str:
        """Return a SHA256 digest suitable for file names."""
        return sha256(
            self.canonical.encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """Cached raw response and associated metadata."""

    key: CacheKey
    content: bytes
    stored_at: datetime
    status_code: int = 200
    headers: Headers = field(default_factory=dict)
    request_id: str | None = None
    metadata: dict[str, CacheMetadataValue] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Validate and normalize cached response data."""
        stored_at = self.stored_at

        if stored_at.tzinfo is None:
            raise ValueError(
                "stored_at must be timezone-aware"
            )

        if not 100 <= self.status_code <= 599:
            raise ValueError(
                "status_code must be between 100 and 599"
            )

        request_id = self.request_id
        if request_id is not None:
            request_id = request_id.strip() or None

        object.__setattr__(
            self,
            "stored_at",
            stored_at.astimezone(UTC),
        )
        object.__setattr__(
            self,
            "headers",
            dict(self.headers),
        )
        object.__setattr__(
            self,
            "request_id",
            request_id,
        )
        object.__setattr__(
            self,
            "metadata",
            dict(self.metadata),
        )

    def age_seconds(
        self,
        *,
        now: datetime | None = None,
    ) -> float:
        """Return cache entry age in seconds."""
        current_time = (
            datetime.now(UTC)
            if now is None
            else _normalize_datetime(now)
        )

        age = (
            current_time - self.stored_at
        ).total_seconds()

        return max(age, 0.0)

    def status(
        self,
        policy: CachePolicy,
        *,
        now: datetime | None = None,
    ) -> CacheStatus:
        """Return cache freshness under the supplied policy."""
        if self.age_seconds(now=now) <= policy.ttl_seconds:
            return CacheStatus.FRESH

        return CacheStatus.STALE

    def is_usable(
        self,
        policy: CachePolicy,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Return whether the entry may be served."""
        cache_status = self.status(
            policy,
            now=now,
        )

        return (
            cache_status is CacheStatus.FRESH
            or policy.allow_stale
        )

    @property
    def expires_at_default(self) -> datetime:
        """Return expiration using the default cache policy."""
        return self.stored_at + timedelta(seconds=300)


def _normalize_datetime(value: datetime) -> datetime:
    """Require and normalize a timezone-aware datetime."""
    if value.tzinfo is None:
        raise ValueError(
            "datetime value must be timezone-aware"
        )

    return value.astimezone(UTC)
