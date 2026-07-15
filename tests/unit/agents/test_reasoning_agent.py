from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast, get_type_hints

import pytest

from ai_parametric_architect.agents import (
    CONSTRAINT_REASONING_AGENT_NAME,
    CONSTRAINT_REASONING_AGENT_VERSION,
    Agent,
    AgentContractError,
    ConstraintReasoningAgent,
)
from ai_parametric_architect.domain import PlanningContextError, Severity, ValidationIssue
from ai_parametric_architect.ports import ConstraintSolver
from ai_parametric_architect.reasoning import (
    ConstraintResolutionPlan,
    ReasoningStatus,
    RuleBasedConstraintSolver,
)


def _issue(*, severity: Severity = Severity.ERROR) -> ValidationIssue:
    return ValidationIssue(
        code="ROOM_OVERLAP",
        severity=severity,
        message="Rooms overlap.",
        path="/entities/rooms",
        entity_ids=("rom_a", "rom_b"),
    )


def _manual_plan(issue: ValidationIssue) -> ConstraintResolutionPlan:
    return ConstraintResolutionPlan(
        issue_code=issue.code,
        issue_path=issue.path,
        entity_ids=issue.entity_ids,
        status=ReasoningStatus.MANUAL_REVIEW_REQUIRED,
        candidates=(),
    )


class RecordingSolver:
    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []

    def solve(self, issue: ValidationIssue) -> ConstraintResolutionPlan:
        self.issues.append(issue)
        return _manual_plan(issue)


class MalformedSolver:
    def solve(self, issue: ValidationIssue) -> ConstraintResolutionPlan:
        return cast(ConstraintResolutionPlan, {"status": "manual_review_required"})


class MismatchedSolver:
    def solve(self, issue: ValidationIssue) -> ConstraintResolutionPlan:
        return ConstraintResolutionPlan(
            issue_code="WALL_ZERO_LENGTH",
            issue_path=issue.path,
            entity_ids=issue.entity_ids,
            status=ReasoningStatus.MANUAL_REVIEW_REQUIRED,
            candidates=(),
        )


class FailingSolver:
    def solve(self, issue: ValidationIssue) -> ConstraintResolutionPlan:
        raise PlanningContextError("Cannot reason about the issue.", path="/issue")


def _accept_agent(
    agent: Agent[ValidationIssue, ConstraintResolutionPlan],
) -> Agent[ValidationIssue, ConstraintResolutionPlan]:
    return agent


def _accept_solver(
    solver: ConstraintSolver[ConstraintResolutionPlan],
) -> ConstraintSolver[ConstraintResolutionPlan]:
    return solver


def test_reasoning_agent_conforms_to_agent_and_solver_protocols() -> None:
    agent = ConstraintReasoningAgent(RecordingSolver())

    assert isinstance(agent, Agent)
    assert _accept_agent(agent) is agent
    assert _accept_solver(agent) is agent
    assert agent.name == CONSTRAINT_REASONING_AGENT_NAME == "constraint-reasoning-agent"
    assert agent.version == CONSTRAINT_REASONING_AGENT_VERSION == "1.0.0"


def test_constraint_solver_annotations_are_runtime_resolvable() -> None:
    hints = get_type_hints(ConstraintSolver.solve)

    assert "return" in hints


def test_run_and_solve_delegate_without_modifying_issue() -> None:
    issue = _issue()
    before = issue.to_dict()
    solver = RecordingSolver()
    agent = ConstraintReasoningAgent(solver)

    assert agent.run(issue) == _manual_plan(issue)
    assert agent.solve(issue) == _manual_plan(issue)
    assert solver.issues == [issue, issue]
    assert solver.issues[0] is issue
    assert solver.issues[1] is issue
    assert issue.to_dict() == before


def test_invalid_input_is_rejected_before_invoking_solver() -> None:
    solver = RecordingSolver()
    agent = ConstraintReasoningAgent(solver)

    with pytest.raises(AgentContractError) as captured:
        agent.run(cast(Any, {"code": "ROOM_OVERLAP"}))

    assert solver.issues == []
    assert captured.value.to_dict() == {
        "code": "AGENT_CONTRACT_VIOLATION",
        "path": "/input",
        "message": "Constraint reasoner input is not a ValidationIssue.",
        "details": {
            "agent": "constraint-reasoning-agent",
            "actual_type": "dict",
            "expected_type": "ValidationIssue",
        },
    }


def test_non_error_input_is_rejected_before_invoking_solver() -> None:
    solver = RecordingSolver()
    agent = ConstraintReasoningAgent(solver)

    with pytest.raises(AgentContractError) as captured:
        agent.run(_issue(severity=Severity.WARNING))

    assert solver.issues == []
    assert captured.value.path == "/input/severity"
    assert captured.value.details == {
        "agent": "constraint-reasoning-agent",
        "actual_severity": "warning",
        "expected_severity": "error",
    }


def test_malformed_severity_is_a_contract_error() -> None:
    issue = _issue()
    object.__setattr__(issue, "severity", "error")

    with pytest.raises(AgentContractError) as captured:
        ConstraintReasoningAgent(RecordingSolver()).run(issue)

    assert captured.value.path == "/input/severity"
    assert captured.value.details == {
        "agent": "constraint-reasoning-agent",
        "actual_type": "str",
        "expected_type": "Severity",
    }


@pytest.mark.parametrize(
    ("field", "value", "path"),
    [
        ("code", "room overlap", "/input/code"),
        ("path", "/entities/~2bad", "/input/path"),
        ("entity_ids", ("rom_a", "rom_a"), "/input/entity_ids"),
        ("message", "", "/input/message"),
        ("details", [], "/input/details"),
    ],
)
def test_malformed_issue_snapshot_is_rejected_before_custom_solver(
    field: str,
    value: object,
    path: str,
) -> None:
    issue = _issue()
    object.__setattr__(issue, field, value)
    solver = RecordingSolver()

    with pytest.raises(AgentContractError) as captured:
        ConstraintReasoningAgent(solver).run(issue)

    assert solver.issues == []
    assert captured.value.path == path
    assert captured.value.details["agent"] == "constraint-reasoning-agent"


def test_malformed_solver_output_raises_structured_contract_error() -> None:
    with pytest.raises(AgentContractError) as captured:
        ConstraintReasoningAgent(MalformedSolver()).run(_issue())

    assert captured.value.to_dict() == {
        "code": "AGENT_CONTRACT_VIOLATION",
        "path": "/output",
        "message": ("Constraint solver returned a value that is not a ConstraintResolutionPlan."),
        "details": {
            "agent": "constraint-reasoning-agent",
            "actual_type": "dict",
            "expected_type": "ConstraintResolutionPlan",
        },
    }


def test_mismatched_solver_output_is_rejected() -> None:
    with pytest.raises(AgentContractError) as captured:
        ConstraintReasoningAgent(MismatchedSolver()).run(_issue())

    assert captured.value.path == "/output"
    assert captured.value.details == {
        "agent": "constraint-reasoning-agent",
        "reason": "ISSUE_MISMATCH",
    }


def test_solver_domain_errors_propagate_unchanged() -> None:
    with pytest.raises(PlanningContextError) as captured:
        ConstraintReasoningAgent(FailingSolver()).run(_issue())

    assert captured.value.path == "/issue"


def test_real_solver_produces_candidate_plan_through_agent() -> None:
    plan = ConstraintReasoningAgent(RuleBasedConstraintSolver()).run(_issue())

    assert plan.status is ReasoningStatus.CANDIDATES_AVAILABLE
    assert len(plan.candidates) == 2


def test_agent_is_frozen_slotted_and_hides_injected_solver_from_repr() -> None:
    agent = ConstraintReasoningAgent(RecordingSolver())

    with pytest.raises((AttributeError, FrozenInstanceError)):
        agent._solver = RecordingSolver()  # type: ignore[misc]

    assert repr(agent) == "ConstraintReasoningAgent()"
    assert "RecordingSolver" not in repr(agent)
    assert not hasattr(agent, "__dict__")
