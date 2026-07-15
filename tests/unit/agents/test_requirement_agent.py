from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from ai_parametric_architect.agents import (
    REQUIREMENT_AGENT_NAME,
    REQUIREMENT_AGENT_VERSION,
    Agent,
    AgentContractError,
    RequirementAgent,
)
from ai_parametric_architect.domain import DesignIntent, RequirementParseError
from ai_parametric_architect.ports import RequirementParser


class RecordingParser:
    def __init__(self, result: DesignIntent) -> None:
        self.result = result
        self.requirements: list[str] = []

    def parse(self, requirement: str) -> DesignIntent:
        self.requirements.append(requirement)
        return self.result


class FailingParser:
    def parse(self, requirement: str) -> DesignIntent:
        raise RequirementParseError(
            "The deterministic grammar does not support this requirement.",
            path="/rooms",
            details={"reason": "UNSUPPORTED_REQUIREMENT"},
        )


class MalformedParser:
    def parse(self, requirement: str) -> DesignIntent:
        return cast(DesignIntent, {"area": 120})


def _intent() -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=120,
        rooms=("bedroom", "bedroom", "bedroom"),
        orientation="south",
    )


def _accept_agent(agent: Agent[str, DesignIntent]) -> Agent[str, DesignIntent]:
    return agent


def _accept_parser(parser: RequirementParser) -> RequirementParser:
    return parser


def test_requirement_agent_conforms_to_agent_and_parser_protocols() -> None:
    agent = RequirementAgent(RecordingParser(_intent()))

    assert isinstance(agent, Agent)
    assert _accept_agent(agent) is agent
    assert _accept_parser(agent) is agent
    assert agent.name == REQUIREMENT_AGENT_NAME == "requirement-agent"
    assert agent.version == REQUIREMENT_AGENT_VERSION == "1.0.0"


def test_run_delegates_deterministically_and_preserves_exact_input() -> None:
    intent = _intent()
    parser = RecordingParser(intent)
    agent = RequirementAgent(parser)
    requirement = "  设计一个１２０㎡三室住宅\n"

    first = agent.run(requirement)
    second = agent.run(requirement)

    assert first is intent
    assert second is intent
    assert parser.requirements == [requirement, requirement]


def test_parse_delegates_to_the_same_agent_boundary() -> None:
    intent = _intent()
    parser = RecordingParser(intent)
    agent = RequirementAgent(parser)

    assert agent.parse("Create a 120 sqm three bedroom house") is intent
    assert parser.requirements == ["Create a 120 sqm three bedroom house"]


def test_parser_domain_errors_propagate_unchanged() -> None:
    agent = RequirementAgent(FailingParser())

    with pytest.raises(RequirementParseError) as captured:
        agent.run("unsupported")

    assert captured.value.code == "REQUIREMENT_PARSE_FAILED"
    assert captured.value.path == "/rooms"
    assert captured.value.details == {"reason": "UNSUPPORTED_REQUIREMENT"}


def test_malformed_parser_output_raises_structured_contract_error() -> None:
    agent = RequirementAgent(MalformedParser())

    with pytest.raises(AgentContractError) as captured:
        agent.run("Create a house")

    assert captured.value.to_dict() == {
        "code": "AGENT_CONTRACT_VIOLATION",
        "path": "/output",
        "message": "Requirement parser returned a value that is not a DesignIntent.",
        "details": {
            "agent": "requirement-agent",
            "actual_type": "dict",
            "expected_type": "DesignIntent",
        },
    }


def test_agent_has_no_mutable_execution_state() -> None:
    parser = RecordingParser(_intent())
    agent = RequirementAgent(parser)

    with pytest.raises((AttributeError, FrozenInstanceError)):
        agent._parser = RecordingParser(_intent())  # type: ignore[misc]

    assert agent.run("same input") == agent.run("same input")
    assert not hasattr(agent, "__dict__")


def test_agent_repr_does_not_expose_injected_parser() -> None:
    agent = RequirementAgent(RecordingParser(_intent()))

    assert repr(agent) == "RequirementAgent()"
    assert "RecordingParser" not in repr(agent)
