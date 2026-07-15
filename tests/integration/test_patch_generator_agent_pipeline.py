from __future__ import annotations

from typing import Any

import pytest

import ai_parametric_architect.composition as composition
from ai_parametric_architect.agents import (
    PatchGenerationRequest,
    PatchGeneratorAgent,
)
from ai_parametric_architect.composition import (
    create_architecture_planner_agent,
    create_editing_service,
    create_patch_generator_agent,
    create_planning_service,
    create_requirement_agent,
)
from ai_parametric_architect.domain import (
    AuditActorType,
    ModelRevision,
    PatchProposal,
    TrustedAuditIdentity,
)
from ai_parametric_architect.planning import FloorPlanProposal, RuleBasedPlanner

AUDIT_IDENTITY = TrustedAuditIdentity(
    actor_id="patch-pipeline-test",
    actor_type=AuditActorType.SYSTEM,
    trace_id="trace:patch-pipeline-test",
)
PLANNING_IDENTITY = TrustedAuditIdentity(
    actor_id="patch-generator-agent",
    actor_type=AuditActorType.AGENT,
    agent_version="test-v1",
    trace_id="trace:patch-planning-test",
)


class RecordingPatchGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[FloorPlanProposal, ModelRevision]] = []

    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None:
        self.calls.append((plan, current_revision))
        return RuleBasedPlanner().generate(plan, current_revision)


def test_patch_agent_proposes_without_mutating_and_trusted_service_commits(
    valid_simple_house: dict[str, Any],
) -> None:
    editing = create_editing_service()
    editing.initialize(
        valid_simple_house,
        provenance="fixture:task-5-patch-agent",
        rationale="Initialize a validated immutable revision.",
        audit_identity=AUDIT_IDENTITY,
    )
    intent = create_requirement_agent().run("Create a 60 sqm one bedroom house")
    plan = create_architecture_planner_agent().run(intent)
    current = editing.current("mdl_simple_house")
    request = PatchGenerationRequest(plan=plan, current_revision=current)
    agent = create_patch_generator_agent()

    first = agent.run(request)
    second = agent.run(request)

    assert isinstance(agent, PatchGeneratorAgent)
    assert first is not None
    assert second is not None
    assert first == second
    assert first.base_revision == current.revision_number
    assert first.affected_entity_ids == ("rom_living",)
    assert all("geometry" not in operation.path for operation in first.operations)
    assert editing.current("mdl_simple_house") == current

    committed = editing.apply_patch(
        "mdl_simple_house",
        first,
        audit_identity=AUDIT_IDENTITY,
    )

    assert committed.revision_number == current.revision_number + 1
    assert committed.parent_revision == current.revision_number
    assert editing.audit_log("mdl_simple_house")[-1].details["affected_entity_ids"] == [
        "rom_living"
    ]


def test_production_planning_pipeline_invokes_patch_generator_agent(
    valid_simple_house: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editing = create_editing_service()
    editing.initialize(
        valid_simple_house,
        provenance="fixture:task-5-composition",
        rationale="Initialize a valid planning context.",
        audit_identity=AUDIT_IDENTITY,
    )
    recorder = RecordingPatchGenerator()
    patch_agent = PatchGeneratorAgent(recorder)
    monkeypatch.setattr(
        composition,
        "create_patch_generator_agent",
        lambda: patch_agent,
    )

    result = create_planning_service(
        editing,
        audit_identity=PLANNING_IDENTITY,
    ).propose(
        "mdl_simple_house",
        "Create a 60 sqm one bedroom house",
    )

    assert result.proposal is not None
    assert len(recorder.calls) == 1
    plan, revision = recorder.calls[0]
    assert plan.intent == result.intent
    assert revision == result.base_revision
    assert editing.current("mdl_simple_house") == result.base_revision
