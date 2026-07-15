from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast, get_type_hints

import pytest

from ai_parametric_architect.agents.base import Agent
from ai_parametric_architect.agents.planner_agent import (
    ARCHITECTURE_PLANNER_AGENT_NAME,
    ARCHITECTURE_PLANNER_AGENT_VERSION,
    ArchitecturePlannerAgent,
)
from ai_parametric_architect.agents.requirement_agent import AgentContractError
from ai_parametric_architect.domain import DesignIntent, PlanningContextError
from ai_parametric_architect.planning.models import FloorPlanProposal, FloorPlanRoom
from ai_parametric_architect.ports import FloorPlanPlanner


def _intent() -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=60,
        rooms=("living", "bedroom"),
        orientation="south",
    )


def _proposal(intent: DesignIntent) -> FloorPlanProposal:
    return FloorPlanProposal(
        intent=intent,
        rooms=(
            FloorPlanRoom(plan_id="plan_room_001", room_type="living", target_area=30),
            FloorPlanRoom(plan_id="plan_room_002", room_type="bedroom", target_area=30),
        ),
        spatial_constraints=(),
        orientation="south",
        strategy="equal-area-stable-order-v1",
    )


class RecordingPlanner:
    def __init__(self) -> None:
        self.intents: list[DesignIntent] = []

    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        self.intents.append(intent)
        return _proposal(intent)


class FailingPlanner:
    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        raise PlanningContextError(
            "The area cannot be allocated.",
            path="/intent/area",
            details={"reason": "NON_POSITIVE_EQUAL_SHARE"},
        )


class MalformedPlanner:
    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        return cast(FloorPlanProposal, {"rooms": []})


class EquivalentIntentPlanner:
    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        replacement = DesignIntent.from_dict(intent.to_dict())
        assert replacement == intent and replacement is not intent
        return _proposal(replacement)


class MismatchedIntentPlanner:
    def plan(self, intent: DesignIntent) -> FloorPlanProposal:
        replacement = DesignIntent(
            building_type="villa",
            area=60,
            rooms=("living", "bedroom"),
            orientation="south",
        )
        return _proposal(replacement)


def _accept_agent(
    agent: Agent[DesignIntent, FloorPlanProposal],
) -> Agent[DesignIntent, FloorPlanProposal]:
    return agent


def _accept_planner(
    planner: FloorPlanPlanner[FloorPlanProposal],
) -> FloorPlanPlanner[FloorPlanProposal]:
    return planner


def test_architecture_planner_agent_conforms_to_agent_and_planner_protocols() -> None:
    agent = ArchitecturePlannerAgent(RecordingPlanner())

    assert isinstance(agent, Agent)
    assert _accept_agent(agent) is agent
    assert _accept_planner(agent) is agent
    assert agent.name == ARCHITECTURE_PLANNER_AGENT_NAME == "architecture-planner-agent"
    assert agent.version == ARCHITECTURE_PLANNER_AGENT_VERSION == "2.0.0"


def test_floor_plan_port_annotations_are_runtime_resolvable() -> None:
    annotations = get_type_hints(FloorPlanPlanner.plan)

    assert annotations["intent"] is DesignIntent
    assert annotations["return"] is not Any


def test_run_and_plan_delegate_and_retain_exact_intent_identity() -> None:
    intent = _intent()
    planner = RecordingPlanner()
    agent = ArchitecturePlannerAgent(planner)

    first = agent.run(intent)
    second = agent.plan(intent)

    assert first.intent is intent
    assert second.intent is intent
    assert planner.intents == [intent, intent]
    assert planner.intents[0] is intent
    assert planner.intents[1] is intent


def test_invalid_input_is_rejected_before_invoking_dependency() -> None:
    planner = RecordingPlanner()
    agent = ArchitecturePlannerAgent(planner)

    with pytest.raises(AgentContractError) as captured:
        agent.run(cast(Any, {"building_type": "house"}))

    assert planner.intents == []
    assert captured.value.to_dict() == {
        "code": "AGENT_CONTRACT_VIOLATION",
        "path": "/input",
        "message": "Architecture planner input is not a DesignIntent.",
        "details": {
            "agent": "architecture-planner-agent",
            "actual_type": "dict",
            "expected_type": "DesignIntent",
        },
    }


def test_malformed_planner_output_raises_structured_contract_error() -> None:
    agent = ArchitecturePlannerAgent(MalformedPlanner())

    with pytest.raises(AgentContractError) as captured:
        agent.run(_intent())

    assert captured.value.to_dict() == {
        "code": "AGENT_CONTRACT_VIOLATION",
        "path": "/output",
        "message": "Architecture planner returned a value that is not a FloorPlanProposal.",
        "details": {
            "agent": "architecture-planner-agent",
            "actual_type": "dict",
            "expected_type": "FloorPlanProposal",
        },
    }


def test_equal_but_reconstructed_intent_is_accepted() -> None:
    intent = _intent()

    result = ArchitecturePlannerAgent(EquivalentIntentPlanner()).run(intent)

    assert result.intent == intent
    assert result.intent is not intent


def test_different_output_intent_is_rejected_as_contract_violation() -> None:
    agent = ArchitecturePlannerAgent(MismatchedIntentPlanner())

    with pytest.raises(AgentContractError) as captured:
        agent.run(_intent())

    assert captured.value.to_dict() == {
        "code": "AGENT_CONTRACT_VIOLATION",
        "path": "/output/intent",
        "message": "Architecture planner output does not retain the input DesignIntent.",
        "details": {
            "agent": "architecture-planner-agent",
            "reason": "INTENT_MISMATCH",
        },
    }


def test_planner_domain_errors_propagate_unchanged() -> None:
    agent = ArchitecturePlannerAgent(FailingPlanner())

    with pytest.raises(PlanningContextError) as captured:
        agent.run(_intent())

    assert captured.value.path == "/intent/area"
    assert captured.value.details == {"reason": "NON_POSITIVE_EQUAL_SHARE"}


def test_agent_is_frozen_slotted_and_hides_injected_planner_from_repr() -> None:
    agent = ArchitecturePlannerAgent(RecordingPlanner())

    with pytest.raises((AttributeError, FrozenInstanceError)):
        agent._planner = RecordingPlanner()  # type: ignore[misc]

    assert repr(agent) == "ArchitecturePlannerAgent()"
    assert "RecordingPlanner" not in repr(agent)
    assert not hasattr(agent, "__dict__")
