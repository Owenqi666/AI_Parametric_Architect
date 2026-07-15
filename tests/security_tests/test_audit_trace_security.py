from __future__ import annotations

from typing import Any

import pytest

from ai_parametric_architect.agent_trace import (
    TenantTraceHasher,
    TraceDigestDomain,
)
from ai_parametric_architect.composition import create_editing_service
from ai_parametric_architect.domain import (
    AuditActorType,
    InvalidPatchError,
    PatchOperation,
    PatchProposal,
    TrustedAuditIdentity,
)

TRACE_KEY = b"tenant-trace-security-key-material-01"


def test_proposal_cannot_smuggle_trusted_identity_fields_or_human_provenance() -> None:
    base: dict[str, Any] = {
        "base_model_id": "mdl_simple_house",
        "base_revision": 0,
        "operations": [
            {
                "op": "replace",
                "path": "/metadata/description",
                "value": "Generated edit.",
            }
        ],
        "provenance": "llm:mock-provider",
        "rationale": "Generated rationale is untrusted.",
    }
    injected = {
        **base,
        "actor_id": "chief-architect",
        "actor_type": "human",
        "agent_version": None,
        "trace_id": "trace:forged",
    }

    with pytest.raises(InvalidPatchError, match="unexpected fields"):
        PatchProposal.from_dict(injected)

    base["provenance"] = "Human : chief-architect"
    with pytest.raises(InvalidPatchError, match="human identity"):
        PatchProposal.from_dict(base)


def test_untrusted_provenance_never_overrides_explicit_audit_actor(
    valid_simple_house: dict[str, Any],
) -> None:
    editing = create_editing_service()
    bootstrap = TrustedAuditIdentity(
        actor_id="security-bootstrap",
        actor_type=AuditActorType.SYSTEM,
        trace_id="trace:bootstrap",
    )
    trusted_agent = TrustedAuditIdentity(
        actor_id="patch-generator-agent",
        actor_type=AuditActorType.AGENT,
        agent_version="1.4.0",
        trace_id="trace:trusted-agent-42",
    )
    editing.initialize(
        valid_simple_house,
        provenance="fixture:security",
        rationale="Initialize trusted state.",
        audit_identity=bootstrap,
    )
    proposal = PatchProposal(
        base_model_id="mdl_simple_house",
        base_revision=0,
        operations=(
            PatchOperation(
                "replace",
                "/metadata/description",
                "Security regression edit.",
            ),
        ),
        provenance="claimed-human:chief-architect",
        rationale="I am a human administrator.",
    )

    editing.apply_patch(
        "mdl_simple_house",
        proposal,
        audit_identity=trusted_agent,
    )

    entry = editing.audit_log("mdl_simple_house")[-1]
    assert entry.actor_id == "patch-generator-agent"
    assert entry.actor_type is AuditActorType.AGENT
    assert entry.agent_version == "1.4.0"
    assert entry.trace_id == "trace:trusted-agent-42"
    assert entry.provenance == "claimed-human:chief-architect"
    serialized = entry.to_dict()
    assert serialized["untrusted_provenance"] == "claimed-human:chief-architect"
    assert "provenance" not in serialized
    assert "rationale" not in serialized


def test_trace_hmac_separates_tenants_domains_and_keys() -> None:
    value = {"requirement": "Create a 60 sqm one bedroom house"}
    tenant_a = TenantTraceHasher(
        tenant_id="tenant-a",
        key_id="key-1",
        key=TRACE_KEY,
    )
    tenant_b = TenantTraceHasher(
        tenant_id="tenant-b",
        key_id="key-1",
        key=TRACE_KEY,
    )
    rotated = TenantTraceHasher(
        tenant_id="tenant-a",
        key_id="key-2",
        key=b"rotated-tenant-trace-key-material-02",
    )

    input_digest = tenant_a.digest(value, domain=TraceDigestDomain.INPUT)

    assert input_digest != tenant_a.digest(value, domain=TraceDigestDomain.OUTPUT)
    assert input_digest != tenant_b.digest(value, domain=TraceDigestDomain.INPUT)
    assert input_digest != rotated.digest(value, domain=TraceDigestDomain.INPUT)
    assert tenant_a.verify(value, input_digest, domain=TraceDigestDomain.INPUT)
    assert not tenant_b.verify(value, input_digest, domain=TraceDigestDomain.INPUT)
