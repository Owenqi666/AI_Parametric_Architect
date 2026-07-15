from __future__ import annotations

from ai_parametric_architect.agents import Agent, RequirementAgent
from ai_parametric_architect.composition import create_requirement_agent
from ai_parametric_architect.domain import DesignIntent


def test_composed_requirement_agent_parses_the_roadmap_example_deterministically() -> None:
    agent = create_requirement_agent()
    requirement = "Create a 120 sqm three bedroom house"

    first = agent.run(requirement)
    second = agent.run(requirement)

    assert isinstance(agent, RequirementAgent)
    assert isinstance(agent, Agent)
    assert first == second
    assert first.to_dict() == {
        "building_type": "house",
        "area": 120,
        "rooms": ["bedroom", "bedroom", "bedroom"],
        "orientation": None,
    }


def test_requirement_agent_output_is_an_intent_not_a_world_model() -> None:
    result = create_requirement_agent().run("设计一个120平方米三室住宅")

    assert isinstance(result, DesignIntent)
    assert set(result.to_dict()).isdisjoint(
        {"entities", "geometry_settings", "model_id", "revision", "root_building_id"}
    )
