from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pytest

import ai_parametric_architect.composition as composition
from ai_parametric_architect.agents import ArchitecturePlannerAgent, RequirementAgent
from ai_parametric_architect.composition import create_editing_service, create_service
from ai_parametric_architect.domain import (
    AuditActorType,
    PatchProposal,
    RevisionNotFoundError,
    TrustedAuditIdentity,
)
from ai_parametric_architect.infrastructure import (
    OpenAIProviderConfig,
    OpenAIResponsesProvider,
)
from ai_parametric_architect.llm import LLMRequirementParser
from ai_parametric_architect.planning import (
    CP_SAT_STRATEGY,
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    ConstraintFloorPlanPlanner,
    FloorPlanProposal,
)
from ai_parametric_architect.repositories import InMemoryRevisionRepository

MODEL_ID = "mdl_simple_house"
AUDIT_IDENTITY = TrustedAuditIdentity(
    actor_id="openai-solver-pipeline-test",
    actor_type=AuditActorType.SYSTEM,
    trace_id="trace:openai-solver-pipeline-test",
)
INTENT_PAYLOAD = {
    "building_type": "house",
    "area": 120,
    "rooms": ["bedroom", "bedroom", "bedroom"],
    "orientation": "south",
    "spatial_constraints": [],
}
_FORBIDDEN_WRITE_CAPABILITIES = (
    "apply_patch",
    "authorize",
    "commit",
    "commit_patch",
    "commit_restoration",
    "head",
    "initialize",
    "repository",
    "_repository",
)


@dataclass(frozen=True, slots=True)
class _OutputText:
    text: str
    type: str = "output_text"


@dataclass(frozen=True, slots=True)
class _AssistantMessage:
    content: list[_OutputText]
    type: str = "message"
    role: str = "assistant"
    status: str = "completed"


@dataclass(frozen=True, slots=True)
class _CompletedResponse:
    output: list[_AssistantMessage]
    status: str = "completed"
    error: None = None


class _FakeResponses:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = deepcopy(payload)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> object:
        self.calls.append(deepcopy(kwargs))
        text = json.dumps(
            self._payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return _CompletedResponse(output=[_AssistantMessage(content=[_OutputText(text)])])


class _FakeOpenAIClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.responses = _FakeResponses(payload)


def _provider() -> tuple[OpenAIResponsesProvider, _FakeOpenAIClient, OpenAIProviderConfig]:
    config = OpenAIProviderConfig(model="gpt-5-mini")
    client = _FakeOpenAIClient(INTENT_PAYLOAD)
    return OpenAIResponsesProvider(config, client=client), client, config


def _revision_history(
    repository: InMemoryRevisionRepository,
) -> tuple[dict[str, object], ...]:
    revisions: list[dict[str, object]] = []
    revision_number = 0
    while True:
        try:
            revisions.append(repository.get(MODEL_ID, revision_number).to_dict())
        except RevisionNotFoundError:
            return tuple(revisions)
        revision_number += 1


def _audit_snapshot(repository: InMemoryRevisionRepository) -> tuple[dict[str, object], ...]:
    return tuple(entry.to_dict() for entry in repository.audit_log(MODEL_ID))


def test_real_openai_adapter_to_cp_sat_produces_only_a_detached_v2_proposal(
    valid_simple_house: dict[str, Any],
) -> None:
    source_document = deepcopy(valid_simple_house)
    repository = InMemoryRevisionRepository()
    editing = create_editing_service(repository)
    editing.initialize(
        valid_simple_house,
        provenance="fixture:openai-solver-pipeline",
        rationale="Initialize the authoritative model before detached planning.",
        audit_identity=AUDIT_IDENTITY,
    )
    render_service = create_service()

    authoritative_world_before = repository.head(MODEL_ID).document
    head_before = repository.head(MODEL_ID).to_dict()
    history_before = _revision_history(repository)
    audit_before = _audit_snapshot(repository)
    render_ir_before = render_service.render_ir(repository.head(MODEL_ID).document).to_dict()

    provider, client, _config = _provider()
    solver_planner = ConstraintFloorPlanPlanner()
    requirement_agent = RequirementAgent(LLMRequirementParser(provider))
    planner_agent = ArchitecturePlannerAgent(solver_planner)

    intent = requirement_agent.run("Create a 120 sqm three bedroom south-facing house")
    proposal = planner_agent.run(intent)

    assert type(proposal) is FloorPlanProposal
    assert not isinstance(proposal, PatchProposal)
    assert proposal.schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION
    assert proposal.strategy == CP_SAT_STRATEGY
    assert proposal.intent == intent
    assert proposal.boundary is not None
    assert all(
        room.is_placed
        and room.x is not None
        and room.y is not None
        and room.width is not None
        and room.height is not None
        for room in proposal.rooms
    )
    serialized_rooms = proposal.to_dict()["rooms"]
    assert isinstance(serialized_rooms, list)
    assert all(
        isinstance(room, dict) and {"x", "y", "width", "height", "orientation"}.issubset(room)
        for room in serialized_rooms
    )
    assert len(serialized_rooms) == len(proposal.rooms)

    assert len(client.responses.calls) == 1
    request = client.responses.calls[0]
    assert request["store"] is False
    assert request["tools"] == []
    assert request["truncation"] == "disabled"

    assert valid_simple_house == source_document
    assert repository.head(MODEL_ID).to_dict() == head_before
    assert _revision_history(repository) == history_before
    assert _audit_snapshot(repository) == audit_before
    assert (
        render_service.render_ir(repository.head(MODEL_ID).document).to_dict() == render_ir_before
    )
    assert repository.head(MODEL_ID).document == authoritative_world_before
    assert repository.head(MODEL_ID).document["entities"] == authoritative_world_before["entities"]
    assert all(
        room.plan_id not in json.dumps(repository.head(MODEL_ID).document, sort_keys=True)
        for room in proposal.rooms
    )

    for component in (provider, solver_planner, solver_planner.solver):
        assert all(
            not hasattr(component, capability) for capability in _FORBIDDEN_WRITE_CAPABILITIES
        )


def test_openai_requirement_agent_is_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, client, config = _provider()
    constructed_with: list[OpenAIProviderConfig] = []

    def fake_provider_factory(value: OpenAIProviderConfig) -> OpenAIResponsesProvider:
        constructed_with.append(value)
        return provider

    monkeypatch.setattr(composition, "OpenAIResponsesProvider", fake_provider_factory)

    default_agent = composition.create_requirement_agent()
    default_intent = default_agent.run("Create a 60 sqm one bedroom house")

    assert constructed_with == []
    assert client.responses.calls == []
    assert default_intent.area == 60
    assert default_intent.rooms == ("bedroom",)

    network_agent = composition.create_openai_requirement_agent(config)
    network_intent = network_agent.run("Create a 120 sqm three bedroom house")

    assert constructed_with == [config]
    assert len(client.responses.calls) == 1
    assert network_intent.to_dict() == {
        key: value for key, value in INTENT_PAYLOAD.items() if key != "spatial_constraints"
    }
