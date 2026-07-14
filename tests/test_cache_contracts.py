"""Tests for typed cache contracts."""

from datetime import UTC, datetime, timedelta

import pytest

from pipeline_dashboard_api_client.cache_contracts import (
    CacheEntry,
    CacheKey,
    CacheMetadataValue,
    CachePolicy,
    CacheStatus,
)


def test_cache_policy_defaults() -> None:
    """Default policy uses a five-minute TTL."""
    policy = CachePolicy()

    assert policy.ttl_seconds == 300.0
    assert policy.allow_stale is False


@pytest.mark.parametrize(
    "ttl_seconds",
    [
        0.0,
        -1.0,
    ],
)
def test_cache_policy_rejects_invalid_ttl(
    ttl_seconds: float,
) -> None:
    """TTL must be strictly positive."""
    with pytest.raises(
        ValueError,
        match="ttl_seconds",
    ):
        CachePolicy(ttl_seconds=ttl_seconds)


def test_cache_key_normalizes_parts() -> None:
    """Cache key parts are stripped and normalized."""
    key = CacheKey(
        namespace=" radar-dashboard ",
        resource=" /dashboard/ ",
        variant=" default ",
    )

    assert key.namespace == "radar-dashboard"
    assert key.resource == "dashboard"
    assert key.variant == "default"


@pytest.mark.parametrize(
    ("namespace", "resource", "variant"),
    [
        ("", "dashboard", "default"),
        ("radar", "", "default"),
        ("radar", "/", "default"),
        ("radar", "dashboard", ""),
    ],
)
def test_cache_key_rejects_empty_parts(
    namespace: str,
    resource: str,
    variant: str,
) -> None:
    """Every key component must be non-empty."""
    with pytest.raises(ValueError):
        CacheKey(
            namespace=namespace,
            resource=resource,
            variant=variant,
        )


def test_cache_key_canonical_value() -> None:
    """Canonical keys remain stable and readable."""
    key = CacheKey(
        namespace="radar-dashboard",
        resource="summary",
        variant="compact",
    )

    assert key.canonical == (
        "radar-dashboard:summary:compact"
    )


def test_cache_key_digest_is_stable() -> None:
    """Equivalent keys produce identical SHA256 digests."""
    first = CacheKey(
        namespace="radar-dashboard",
        resource="health",
    )
    second = CacheKey(
        namespace=" radar-dashboard ",
        resource="/health/",
    )

    assert first.digest == second.digest
    assert len(first.digest) == 64


def build_entry(
    *,
    stored_at: datetime | None = None,
) -> CacheEntry:
    """Build a reusable cache entry."""
    return CacheEntry(
        key=CacheKey(
            namespace="radar-dashboard",
            resource="dashboard",
        ),
        content=b'{"status":"healthy"}',
        stored_at=(
            datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
            if stored_at is None
            else stored_at
        ),
        headers={
            "Content-Type": "application/json",
        },
        request_id=" request-cache-31 ",
        metadata={
            "source": "network",
        },
    )


def test_cache_entry_normalizes_metadata() -> None:
    """Cache entries normalize timezone and request metadata."""
    entry = build_entry()

    assert entry.stored_at.tzinfo is UTC
    assert entry.request_id == "request-cache-31"
    assert entry.headers == {
        "Content-Type": "application/json"
    }
    assert entry.metadata == {
        "source": "network"
    }


def test_cache_entry_copies_mutable_mappings() -> None:
    """Caller-owned mappings are not retained."""
    headers = {
        "Content-Type": "application/json",
    }
    metadata: dict[str, CacheMetadataValue] = {
        "source": "network",
    }

    entry = CacheEntry(
        key=CacheKey(
            namespace="radar-dashboard",
            resource="summary",
        ),
        content=b"{}",
        stored_at=datetime.now(UTC),
        headers=headers,
        metadata=metadata,
    )

    headers["Content-Type"] = "text/plain"
    metadata["source"] = "changed"

    assert entry.headers["Content-Type"] == (
        "application/json"
    )
    assert entry.metadata["source"] == "network"


def test_cache_entry_rejects_naive_datetime() -> None:
    """Cache timestamps must be timezone-aware."""
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        build_entry(
            stored_at=datetime(2026, 7, 14, 12, 0)
        )


@pytest.mark.parametrize(
    "status_code",
    [
        99,
        600,
    ],
)
def test_cache_entry_rejects_invalid_status_code(
    status_code: int,
) -> None:
    """Cached status codes must be valid HTTP status codes."""
    with pytest.raises(
        ValueError,
        match="status_code",
    ):
        CacheEntry(
            key=CacheKey(
                namespace="radar-dashboard",
                resource="dashboard",
            ),
            content=b"{}",
            stored_at=datetime.now(UTC),
            status_code=status_code,
        )


def test_cache_entry_age_seconds() -> None:
    """Entry age is calculated from the stored timestamp."""
    entry = build_entry()
    now = datetime(
        2026,
        7,
        14,
        12,
        2,
        tzinfo=UTC,
    )

    assert entry.age_seconds(now=now) == 120.0


def test_cache_entry_age_never_becomes_negative() -> None:
    """Clock skew does not produce negative cache age."""
    entry = build_entry()
    earlier = datetime(
        2026,
        7,
        14,
        11,
        59,
        tzinfo=UTC,
    )

    assert entry.age_seconds(now=earlier) == 0.0


def test_cache_entry_is_fresh_within_ttl() -> None:
    """Entries inside TTL are marked fresh."""
    entry = build_entry()
    policy = CachePolicy(ttl_seconds=120)
    now = entry.stored_at + timedelta(seconds=119)

    assert entry.status(
        policy,
        now=now,
    ) is CacheStatus.FRESH

    assert entry.is_usable(
        policy,
        now=now,
    ) is True


def test_cache_entry_is_fresh_at_exact_ttl() -> None:
    """TTL boundary remains fresh."""
    entry = build_entry()
    policy = CachePolicy(ttl_seconds=120)
    now = entry.stored_at + timedelta(seconds=120)

    assert entry.status(
        policy,
        now=now,
    ) is CacheStatus.FRESH


def test_cache_entry_is_stale_after_ttl() -> None:
    """Entries beyond TTL are marked stale."""
    entry = build_entry()
    policy = CachePolicy(ttl_seconds=120)
    now = entry.stored_at + timedelta(seconds=121)

    assert entry.status(
        policy,
        now=now,
    ) is CacheStatus.STALE

    assert entry.is_usable(
        policy,
        now=now,
    ) is False


def test_cache_policy_may_allow_stale_entry() -> None:
    """Offline-capable policies may serve stale entries."""
    entry = build_entry()
    policy = CachePolicy(
        ttl_seconds=60,
        allow_stale=True,
    )
    now = entry.stored_at + timedelta(hours=1)

    assert entry.status(
        policy,
        now=now,
    ) is CacheStatus.STALE

    assert entry.is_usable(
        policy,
        now=now,
    ) is True


def test_default_expiration_is_five_minutes() -> None:
    """Default expiration metadata remains deterministic."""
    entry = build_entry()

    assert entry.expires_at_default == (
        entry.stored_at + timedelta(minutes=5)
    )
