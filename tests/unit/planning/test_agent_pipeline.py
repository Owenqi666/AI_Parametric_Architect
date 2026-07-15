from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    DesignIntent,
    ModelRevision,
    PatchOperation,
    PatchProposal,
    PlannerContractError,
    PlanningContextError,
)
from ai_parametric_architect.planning import (
    AgentPlanningPipeline,
    FloorPlanProposal,
    RuleBasedFloorPlanPlanner,
    RuleBasedPlanner,
)
from ai_parametric_architect.ports import ProposalPlanner


def _intent(*, building_type: str = "house") -> DesignIntent:
    return DesignIntent(
        building_type=building_type,
        area=60,
        rooms=("living", "bedroom"),
        orientation="south",
    )


def _revision() -> ModelRevision:
    rooms = {
        "rom_a": {"id": "rom_a", "entity_type": "room", "name": "A"},
        "rom_b": {"id": "rom_b", "entity_type": "room", "name": "B"},
    }
    return ModelRevision(
        model_id="mdl_pipeline",
        revision_number=4,
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
        parent_revision=3,
        document={
            "model_id": "mdl_pipeline",
            "revision": 4,
            "entities": {"rooms": rooms},
        },
    )


def _proposal(
    *,
    base_model_id: str = "mdl_pipeline",
    base_revision: int = 4,
) -> PatchProposal:
    return PatchProposal(
        base_model_id=base_model_id,
        base_revision=base_revision,
        operations=(PatchOperation("replace", "/entities/rooms/rom_a/name", "Living"),),
        provenance="test",
        rationale="Test pipeline ordering.",
        affected_entity_ids=("rom_a",),
    )


class RecordingPlanner:
    def __init__(self, events: list[str], plan: FloorPlanProposal) -> None:
        self.events = events
        self.plan_value = plan
        self.inputs: list[DesignIntent] = []

    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        self.events.append("plan")
        self.inputs.append(intent)
        return self.plan_value


class RecordingGenerator:
    def __init__(self, events: list[str], result: PatchProposal | None) -> None:
        self.events = events
        self.result = result
        self.inputs: list[tuple[FloorPlanProposal, ModelRevision]] = []

    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None:
        self.events.append("generate")
        self.inputs.append((plan, current_revision))
        return self.result


class MalformedPlanner:
    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        return cast(FloorPlanProposal, {"intent": intent.to_dict()})


class MalformedGenerator:
    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None:
        return cast(PatchProposal, {"operations": []})


class FailingPlanner:
    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        raise PlanningContextError("Cannot plan.", path="/intent")


def _accept_planner(planner: ProposalPlanner) -> ProposalPlanner:
    return planner


def test_pipeline_orders_dependencies_and_preserves_all_input_identities() -> None:
    intent = _intent()
    revision = _revision()
    floor_plan = RuleBasedFloorPlanPlanner().plan(intent)
    proposal = _proposal()
    events: list[str] = []
    planner = RecordingPlanner(events, floor_plan)
    generator = RecordingGenerator(events, proposal)
    pipeline = AgentPlanningPipeline(planner, generator)

    result = pipeline.plan(intent, revision)

    assert _accept_planner(pipeline) is pipeline
    assert result is proposal
    assert events == ["plan", "generate"]
    assert planner.inputs[0] is intent
    assert generator.inputs[0][0] is floor_plan
    assert generator.inputs[0][1] is revision


def test_pipeline_propagates_none_as_a_no_change_result() -> None:
    intent = _intent()
    events: list[str] = []
    pipeline = AgentPlanningPipeline(
        RecordingPlanner(events, RuleBasedFloorPlanPlanner().plan(intent)),
        RecordingGenerator(events, None),
    )

    assert pipeline.plan(intent, _revision()) is None
    assert events == ["plan", "generate"]


@pytest.mark.parametrize(
    ("intent", "revision", "path"),
    [
        (cast(Any, {}), _revision(), "/intent"),
        (_intent(), cast(Any, {}), "/base_revision"),
    ],
)
def test_pipeline_rejects_invalid_inputs_before_dependencies(
    intent: DesignIntent,
    revision: ModelRevision,
    path: str,
) -> None:
    events: list[str] = []
    valid_intent = _intent()
    pipeline = AgentPlanningPipeline(
        RecordingPlanner(events, RuleBasedFloorPlanPlanner().plan(valid_intent)),
        RecordingGenerator(events, _proposal()),
    )

    with pytest.raises(PlanningContextError) as captured:
        pipeline.plan(intent, revision)

    assert captured.value.path == path
    assert events == []


def test_pipeline_rejects_malformed_or_mismatched_floor_plan() -> None:
    with pytest.raises(PlannerContractError) as malformed:
        AgentPlanningPipeline(MalformedPlanner(), RecordingGenerator([], _proposal())).plan(
            _intent(), _revision()
        )
    assert malformed.value.path == "/floor_plan"

    intent = _intent()
    mismatched = RuleBasedFloorPlanPlanner().plan(_intent(building_type="villa"))
    with pytest.raises(PlannerContractError) as mismatch:
        AgentPlanningPipeline(
            RecordingPlanner([], mismatched), RecordingGenerator([], _proposal())
        ).plan(intent, _revision())
    assert mismatch.value.path == "/floor_plan/intent"


def test_pipeline_rejects_malformed_patch_generator_output() -> None:
    intent = _intent()
    pipeline = AgentPlanningPipeline(
        RecordingPlanner([], RuleBasedFloorPlanPlanner().plan(intent)),
        MalformedGenerator(),
    )

    with pytest.raises(PlannerContractError) as captured:
        pipeline.plan(intent, _revision())

    assert captured.value.path == "/patch_proposal"


@pytest.mark.parametrize(
    ("proposal", "path"),
    [
        (_proposal(base_model_id="mdl_other"), "/patch_proposal/base_model_id"),
        (_proposal(base_revision=3), "/patch_proposal/base_revision"),
    ],
)
def test_pipeline_rejects_patch_bound_to_another_snapshot(
    proposal: PatchProposal,
    path: str,
) -> None:
    intent = _intent()
    pipeline = AgentPlanningPipeline(
        RecordingPlanner([], RuleBasedFloorPlanPlanner().plan(intent)),
        RecordingGenerator([], proposal),
    )

    with pytest.raises(PlannerContractError) as captured:
        pipeline.plan(intent, _revision())

    assert captured.value.path == path


def test_pipeline_propagates_dependency_error_unchanged_and_stops() -> None:
    events: list[str] = []
    generator = RecordingGenerator(events, _proposal())

    with pytest.raises(PlanningContextError) as captured:
        AgentPlanningPipeline(FailingPlanner(), generator).plan(_intent(), _revision())

    assert captured.value.path == "/intent"
    assert events == []
    assert generator.inputs == []


def test_rule_based_planner_generate_alias_matches_direct_plan_conversion() -> None:
    intent = _intent()
    floor_plan = RuleBasedFloorPlanPlanner().plan(intent)
    revision = _revision()
    planner = RuleBasedPlanner()

    assert planner.generate(floor_plan, revision) == planner.plan_from_floor_plan(
        floor_plan, revision
    )


def test_pipeline_is_frozen_slotted_and_hides_dependencies() -> None:
    intent = _intent()
    pipeline = AgentPlanningPipeline(
        RecordingPlanner([], RuleBasedFloorPlanPlanner().plan(intent)),
        RecordingGenerator([], None),
    )

    with pytest.raises((AttributeError, FrozenInstanceError)):
        pipeline._patch_generator = RecordingGenerator([], None)  # type: ignore[misc]

    assert repr(pipeline) == "AgentPlanningPipeline()"
    assert not hasattr(pipeline, "__dict__")
