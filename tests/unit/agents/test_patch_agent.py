from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any, cast, get_type_hints

import pytest

from ai_parametric_architect.agents import Agent, AgentContractError
from ai_parametric_architect.agents.patch_agent import (
    PATCH_GENERATOR_AGENT_NAME,
    PATCH_GENERATOR_AGENT_VERSION,
    PatchGenerationRequest,
    PatchGeneratorAgent,
)
from ai_parametric_architect.domain import (
    DesignIntent,
    ModelRevision,
    PatchOperation,
    PatchProposal,
    PlanningContextError,
)
from ai_parametric_architect.planning import (
    FloorPlanProposal,
    RuleBasedFloorPlanPlanner,
)
from ai_parametric_architect.ports import PatchProposalGenerator


def _plan() -> FloorPlanProposal:
    intent = DesignIntent(
        building_type="house",
        area=60,
        rooms=("living", "bedroom"),
        orientation="south",
    )
    return RuleBasedFloorPlanPlanner().plan(intent)


def _revision(*, entities: object | None = None, revision_number: int = 7) -> ModelRevision:
    registry: object = (
        {
            "rooms": {
                "rom_a": {"id": "rom_a", "entity_type": "room"},
                "rom_b": {"id": "rom_b", "entity_type": "room"},
            },
            "walls": {"wal_a": {"id": "wal_a", "entity_type": "wall"}},
        }
        if entities is None
        else entities
    )
    return ModelRevision(
        model_id="mdl_agent",
        revision_number=revision_number,
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
        parent_revision=revision_number - 1,
        document={
            "model_id": "mdl_agent",
            "revision": revision_number,
            "entities": registry,
        },
    )


def _proposal(
    revision: int = 7,
    *,
    base_model_id: str = "mdl_agent",
    affected_entity_ids: tuple[str, ...] = ("rom_a", "rom_b"),
) -> PatchProposal:
    return PatchProposal(
        base_model_id=base_model_id,
        base_revision=revision,
        operations=(PatchOperation("replace", "/entities/rooms/rom_a/name", "Living"),),
        provenance="agent:patch-generator-v1",
        rationale="Assign requested room semantics.",
        affected_entity_ids=affected_entity_ids,
    )


class RecordingGenerator:
    def __init__(self, result: PatchProposal | None) -> None:
        self.result = result
        self.calls: list[tuple[FloorPlanProposal, ModelRevision]] = []

    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None:
        self.calls.append((plan, current_revision))
        return self.result


class MalformedGenerator:
    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None:
        return cast(PatchProposal, {"operations": []})


class FailingGenerator:
    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None:
        raise PlanningContextError("Cannot map plan.", path="/plan")


class PatchProposalSubclass(PatchProposal):
    pass


def _accept_agent(
    agent: Agent[PatchGenerationRequest, PatchProposal | None],
) -> Agent[PatchGenerationRequest, PatchProposal | None]:
    return agent


def _accept_generator(
    generator: PatchProposalGenerator[FloorPlanProposal],
) -> PatchProposalGenerator[FloorPlanProposal]:
    return generator


def test_patch_agent_conforms_to_agent_and_generator_protocols() -> None:
    agent = PatchGeneratorAgent(RecordingGenerator(_proposal()))

    assert isinstance(agent, Agent)
    assert _accept_agent(agent) is agent
    assert _accept_generator(agent) is agent
    assert agent.name == PATCH_GENERATOR_AGENT_NAME == "patch-generator-agent"
    assert agent.version == PATCH_GENERATOR_AGENT_VERSION == "1.0.0"


def test_patch_generation_port_annotations_are_runtime_resolvable() -> None:
    annotations = get_type_hints(PatchProposalGenerator.generate)

    assert annotations["plan"] is not Any
    assert annotations["current_revision"] is ModelRevision
    assert annotations["return"] is not Any


def test_run_preserves_identity_and_does_not_mutate_inputs() -> None:
    plan = _plan()
    revision = _revision()
    proposal = _proposal()
    generator = RecordingGenerator(proposal)
    before_plan = plan.to_dict()
    before_document = revision.document

    result = PatchGeneratorAgent(generator).run(
        PatchGenerationRequest(plan=plan, current_revision=revision)
    )

    assert result is proposal
    assert generator.calls == [(plan, revision)]
    assert generator.calls[0][0] is plan
    assert generator.calls[0][1] is revision
    assert plan.to_dict() == before_plan
    assert revision.document == before_document


def test_generate_alias_and_none_no_change_are_supported() -> None:
    plan = _plan()
    revision = _revision()
    generator = RecordingGenerator(None)
    agent = PatchGeneratorAgent(generator)

    assert agent.generate(plan, revision) is None
    assert generator.calls == [(plan, revision)]


def test_invalid_request_is_rejected_before_generator_call() -> None:
    generator = RecordingGenerator(_proposal())

    with pytest.raises(AgentContractError) as captured:
        PatchGeneratorAgent(generator).run(cast(Any, {"plan": _plan()}))

    assert captured.value.path == "/input"
    assert captured.value.details["expected_type"] == "PatchGenerationRequest"
    assert generator.calls == []


@pytest.mark.parametrize(
    ("generation_request", "path", "expected_type"),
    [
        (
            PatchGenerationRequest(plan=cast(Any, {}), current_revision=_revision()),
            "/input/plan",
            "FloorPlanProposal",
        ),
        (
            PatchGenerationRequest(plan=_plan(), current_revision=cast(Any, {})),
            "/input/current_revision",
            "ModelRevision",
        ),
    ],
)
def test_invalid_nested_request_values_are_rejected(
    generation_request: PatchGenerationRequest,
    path: str,
    expected_type: str,
) -> None:
    with pytest.raises(AgentContractError) as captured:
        PatchGeneratorAgent(RecordingGenerator(_proposal())).run(generation_request)

    assert captured.value.path == path
    assert captured.value.details["expected_type"] == expected_type


@pytest.mark.parametrize(
    ("generator", "path", "reason"),
    [
        (MalformedGenerator(), "/output", None),
        (
            RecordingGenerator(
                PatchProposalSubclass(
                    base_model_id="mdl_agent",
                    base_revision=7,
                    operations=(PatchOperation("replace", "/entities/rooms/rom_a/name", "Living"),),
                    provenance="agent:patch-generator-v1",
                    rationale="Reject executable proposal subclasses.",
                    affected_entity_ids=("rom_a",),
                )
            ),
            "/output",
            None,
        ),
        (RecordingGenerator(_proposal(6)), "/output/base_revision", "BASE_REVISION_MISMATCH"),
        (
            RecordingGenerator(_proposal(base_model_id="mdl_other")),
            "/output/base_model_id",
            "BASE_MODEL_MISMATCH",
        ),
        (
            RecordingGenerator(_proposal(affected_entity_ids=())),
            "/output/affected_entity_ids",
            "AFFECTED_ENTITY_IDS_EMPTY",
        ),
        (
            RecordingGenerator(_proposal(affected_entity_ids=("rom_a", "rom_unknown"))),
            "/output/affected_entity_ids",
            "UNKNOWN_AFFECTED_ENTITY_IDS",
        ),
    ],
)
def test_malformed_stale_or_untraceable_outputs_are_rejected(
    generator: PatchProposalGenerator[FloorPlanProposal],
    path: str,
    reason: str | None,
) -> None:
    with pytest.raises(AgentContractError) as captured:
        PatchGeneratorAgent(generator).run(
            PatchGenerationRequest(plan=_plan(), current_revision=_revision())
        )

    assert captured.value.path == path
    if reason is not None:
        assert captured.value.details["reason"] == reason
    if reason == "UNKNOWN_AFFECTED_ENTITY_IDS":
        assert captured.value.details["unknown_entity_ids"] == ["rom_unknown"]


@pytest.mark.parametrize("entities", [[], {"rooms": []}, {"rooms": {"": {}}}])
def test_malformed_revision_entity_registry_is_rejected(entities: object) -> None:
    with pytest.raises(AgentContractError) as captured:
        PatchGeneratorAgent(RecordingGenerator(_proposal())).run(
            PatchGenerationRequest(plan=_plan(), current_revision=_revision(entities=entities))
        )

    assert captured.value.path.startswith("/input/current_revision/document/entities")


def test_generator_errors_propagate_unchanged() -> None:
    with pytest.raises(PlanningContextError) as captured:
        PatchGeneratorAgent(FailingGenerator()).generate(_plan(), _revision())

    assert captured.value.path == "/plan"


def test_request_and_agent_are_frozen_slotted_and_hide_dependency() -> None:
    request = PatchGenerationRequest(plan=_plan(), current_revision=_revision())
    agent = PatchGeneratorAgent(RecordingGenerator(_proposal()))

    with pytest.raises((AttributeError, FrozenInstanceError)):
        request.plan = _plan()  # type: ignore[misc]
    with pytest.raises((AttributeError, FrozenInstanceError)):
        agent._generator = RecordingGenerator(None)  # type: ignore[misc]

    assert repr(agent) == "PatchGeneratorAgent()"
    assert not hasattr(request, "__dict__")
    assert not hasattr(agent, "__dict__")
