from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_parametric_architect.agent_trace import (
    TenantTraceHasher,
    TraceDigestDomain,
    canonical_json_hmac_sha256,
)
from ai_parametric_architect.domain import NonJsonValueError

KEY = b"tenant-a-trace-key-material-0001"


def digest(value: object, *, domain: TraceDigestDomain = TraceDigestDomain.INPUT) -> str:
    return canonical_json_hmac_sha256(
        value,
        tenant_id="tenant-a",
        key=KEY,
        domain=domain,
    )


def test_hmac_is_stable_for_canonical_json_object_order() -> None:
    first = {"z": [2, 1], "a": "建筑"}
    second = {"a": "建筑", "z": [2, 1]}

    first_hash = digest(first)

    assert digest(second) == first_hash
    assert len(first_hash) == 64
    assert first_hash == first_hash.lower()


def test_array_order_is_observable_and_input_is_not_modified() -> None:
    value: dict[str, object] = {"rooms": ["living", "bedroom"]}
    before = {"rooms": ["living", "bedroom"]}

    value_digest = digest(value)

    assert value_digest != digest({"rooms": ["bedroom", "living"]})
    assert value == before


@pytest.mark.parametrize(
    "value",
    [
        ("tuple-is-not-json",),
        {"when": datetime(2026, 7, 15, tzinfo=UTC)},
        {"value": float("nan")},
        {"value": float("inf")},
        {1: "non-string key"},
    ],
)
def test_hmac_rejects_values_outside_the_strict_json_boundary(value: object) -> None:
    with pytest.raises(NonJsonValueError):
        digest(value)


def test_hmac_rejects_shared_or_cyclic_containers() -> None:
    shared: list[object] = []
    aliased = {"first": shared, "second": shared}
    cyclic: list[object] = []
    cyclic.append(cyclic)

    with pytest.raises(NonJsonValueError):
        digest(aliased)
    with pytest.raises(NonJsonValueError):
        digest(cyclic)


@pytest.mark.parametrize(
    ("tenant_id", "key", "domain"),
    [
        ("", KEY, "input"),
        ("tenant a", KEY, "input"),
        ("tenant-a", b"short", "input"),
        ("tenant-a", KEY, "unknown"),
    ],
)
def test_hmac_rejects_invalid_security_context(
    tenant_id: str,
    key: bytes,
    domain: str,
) -> None:
    with pytest.raises(ValueError):
        canonical_json_hmac_sha256(
            {},
            tenant_id=tenant_id,
            key=key,
            domain=domain,
        )


def test_tenant_hasher_verifies_with_constant_interface_and_hides_key() -> None:
    hasher = TenantTraceHasher(tenant_id="tenant-a", key_id="key-2026-07", key=KEY)
    value = {"requirement": "three bedrooms"}
    value_digest = hasher.digest(value, domain="input")

    assert hasher.verify(value, value_digest, domain=TraceDigestDomain.INPUT)
    assert not hasher.verify({"requirement": "two bedrooms"}, value_digest, domain="input")
    assert not hasher.verify(value, 7, domain="input")  # type: ignore[arg-type]
    assert KEY.decode() not in repr(hasher)
