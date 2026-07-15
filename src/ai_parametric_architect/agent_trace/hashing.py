"""Tenant-scoped HMAC correlation digests for observable agent boundaries."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from ai_parametric_architect.domain.json_values import ensure_json_value

TRACE_HASH_ALGORITHM: Final = "hmac-sha256-v1"
_HMAC_PROTOCOL_LABEL: Final = b"ai-parametric-architect.agent-trace.hmac.v1\x00"
_MINIMUM_HMAC_KEY_BYTES: Final = 32


class TraceDigestDomain(StrEnum):
    """Separate otherwise identical values observed at different boundaries."""

    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True, slots=True, init=False)
class TenantTraceHasher:
    """Compute deterministic tenant- and domain-separated HMAC digests.

    Digests are correlation/integrity fingerprints, not encryption or privacy
    protection.  Callers must still minimize traced values, control access to
    trace records, and manage a distinct secret key for each tenant.
    """

    tenant_id: str
    key_id: str
    _key: bytes = field(repr=False)

    def __init__(self, *, tenant_id: str, key_id: str, key: bytes) -> None:
        _require_identifier(tenant_id, "tenant_id")
        _require_identifier(key_id, "key_id")
        if not isinstance(key, bytes) or len(key) < _MINIMUM_HMAC_KEY_BYTES:
            raise ValueError("Trace HMAC key must contain at least 32 bytes.")
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "key_id", key_id)
        object.__setattr__(self, "_key", key)

    def digest(
        self,
        value: object,
        *,
        domain: TraceDigestDomain | str,
    ) -> str:
        """Return a correlation digest without retaining the observed value."""

        return canonical_json_hmac_sha256(
            value,
            tenant_id=self.tenant_id,
            key=self._key,
            domain=domain,
        )

    def verify(
        self,
        value: object,
        digest: str,
        *,
        domain: TraceDigestDomain | str,
    ) -> bool:
        """Compare a correlation digest using a timing-safe primitive."""

        if not isinstance(digest, str):
            return False
        expected = self.digest(value, domain=domain)
        return hmac.compare_digest(expected, digest)


def canonical_json_hmac_sha256(
    value: object,
    *,
    tenant_id: str,
    key: bytes,
    domain: TraceDigestDomain | str,
) -> str:
    """HMAC a strict canonical JSON value with tenant and boundary separation.

    This digest supports correlation and tamper detection only.  It is not a
    privacy boundary and must not be presented as anonymization or encryption.
    """

    _require_identifier(tenant_id, "tenant_id")
    if not isinstance(key, bytes) or len(key) < _MINIMUM_HMAC_KEY_BYTES:
        raise ValueError("Trace HMAC key must contain at least 32 bytes.")
    try:
        domain_value = TraceDigestDomain(domain)
    except (TypeError, ValueError) as error:
        raise ValueError("Trace digest domain is not supported.") from error

    canonical = _canonical_json_bytes(value)
    tenant_bytes = tenant_id.encode("utf-8")
    domain_bytes = domain_value.value.encode("ascii")
    message = b"".join(
        (
            _HMAC_PROTOCOL_LABEL,
            len(tenant_bytes).to_bytes(4, "big"),
            tenant_bytes,
            len(domain_bytes).to_bytes(1, "big"),
            domain_bytes,
            canonical,
        )
    )
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    ensure_json_value(value)
    canonical = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return canonical.encode("utf-8")


def _require_identifier(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 128
        or any(character.isspace() or not character.isprintable() for character in value)
    ):
        raise ValueError(f"Trace {field_name} must be a canonical non-empty identifier.")
