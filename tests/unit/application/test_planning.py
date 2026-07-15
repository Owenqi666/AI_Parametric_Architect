from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from ai_parametric_architect.application.authorization import AgentAuthorizationGateway
from ai_parametric_architect.application.editing import EditingService
from ai_parametric_architect.application.planning import (
    ArchitecturePlanningService,
    PlanningCommitResult,
    PlanningProposalResult,
)
from ai_parametric_architect.domain import (
    PLANNING_EXTENSION_KEY,
    AuditActorType,
    DesignIntent,
    ModelRevision,
    PatchOperation,
    PatchProposal,
    PlannerContractError,
    PlanningRecord,
    RevisionConflictError,
    RoomAssignment,
    TrustedAuditIdentity,
)
from ai_parametric_architect.policy import ArchitecturePlanningAuthorizationPolicy

PLANNING_PATH = f"/extensions/{PLANNING_EXTENSION_KEY}"


class FakeParser:
    def __init__(self, result: object, events: list[str]) -> None:
        self.result = result
        self.events = events
        self.requirements: list[str] = []

    def parse(self, requirement: str) -> DesignIntent:
        self.events.append("parse")
        self.requirements.append(requirement)
        return cast(DesignIntent, self.result)


class FakePlanner:
    def __init__(self, result: object, events: list[str]) -> None:
        self.result = result
        self.events = events
        self.calls: list[tuple[DesignIntent, ModelRevision]] = []

    def plan(self, intent: DesignIntent, base_revision: ModelRevision) -> PatchProposal | None:
        self.events.append("plan")
        self.calls.append((intent, base_revision))
        return cast(PatchProposal | None, self.result)


class FakeEditingService(EditingService):
    def __init__(self, base_revision: ModelRevision, events: list[str]) -> None:
        self.base_revision = base_revision
        self.events = events
        self.apply_calls: list[tuple[str, PatchProposal]] = []
        self.audit_identities: list[TrustedAuditIdentity] = []

    def current(self, model_id: str) -> ModelRevision:
        self.events.append("current")
        assert model_id == self.base_revision.model_id
        return self.base_revision

    def apply_patch(
        self,
        model_id: str,
        proposal: PatchProposal,
        *,
        audit_identity: TrustedAuditIdentity,
    ) -> ModelRevision:
        self.events.append("commit")
        self.apply_calls.append((model_id, proposal))
        self.audit_identities.append(audit_identity)
        document = self.base_revision.document
        document["revision"] = self.base_revision.revision_number + 1
        return ModelRevision(
            model_id=model_id,
            revision_number=self.base_revision.revision_number + 1,
            created_at=datetime(2026, 7, 15, 10, 1, tzinfo=UTC),
            parent_revision=self.base_revision.revision_number,
            document=document,
        )


def design_intent(
    *,
    area: int = 120,
    orientation: str | None = "south",
) -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=area,
        rooms=("bedroom",),
        orientation=orientation,
    )


def planning_record(*, intent: DesignIntent | None = None) -> PlanningRecord:
    record_intent = design_intent() if intent is None else intent
    unverified_constraints = {"area", "building_type"}
    if record_intent.orientation is not None:
        unverified_constraints.add("orientation")
    return PlanningRecord(
        intent=record_intent,
        assignments=(RoomAssignment("rom_a", "bedroom", "Bedroom 1"),),
        unverified_constraints=tuple(sorted(unverified_constraints)),
    )


def model_document(
    *,
    revision_number: int = 4,
    room_name: str = "Room A",
    room_usage: object = None,
    extensions: object = None,
) -> dict[str, Any]:
    room: dict[str, Any] = {
        "id": "rom_a",
        "entity_type": "room",
        "name": room_name,
    }
    if room_usage is not None:
        room["usage"] = room_usage
    document: dict[str, Any] = {
        "schema_version": "1.0.0",
        "model_id": "mdl_house",
        "revision": revision_number,
        "entities": {"rooms": {"rom_a": room}},
    }
    if extensions is not None:
        document["extensions"] = deepcopy(extensions)
    return document


def model_revision(
    *,
    revision_number: int = 4,
    room_name: str = "Room A",
    room_usage: object = None,
    extensions: object = None,
) -> ModelRevision:
    document = model_document(
        revision_number=revision_number,
        room_name=room_name,
        room_usage=room_usage,
        extensions=extensions,
    )
    revision_number = cast(int, document["revision"])
    return ModelRevision(
        model_id="mdl_house",
        revision_number=revision_number,
        created_at=datetime(2026, 7, 15, 10, 0, tzinfo=UTC),
        parent_revision=revision_number - 1,
        document=document,
    )


def proposal(
    operations: Sequence[PatchOperation],
    *,
    base_model_id: str = "mdl_house",
    base_revision: int = 4,
    affected_entity_ids: tuple[str, ...] = ("rom_a",),
) -> PatchProposal:
    return PatchProposal(
        base_model_id=base_model_id,
        base_revision=base_revision,
        operations=tuple(operations),
        provenance="planner:test-v1",
        rationale="Assign requested room semantics and record planning intent.",
        affected_entity_ids=affected_entity_ids,
    )


def canonical_operations(record: PlanningRecord) -> tuple[PatchOperation, ...]:
    return (
        PatchOperation("add", "/entities/rooms/rom_a/usage", "bedroom"),
        PatchOperation("replace", "/entities/rooms/rom_a/name", "Bedroom 1"),
        PatchOperation("add", PLANNING_PATH, record.to_dict()),
    )


def service(
    planner_result: object,
    *,
    base_revision: ModelRevision | None = None,
    parser_result: object | None = None,
) -> tuple[ArchitecturePlanningService, FakeParser, FakePlanner, FakeEditingService, list[str]]:
    events: list[str] = []
    parser = FakeParser(design_intent() if parser_result is None else parser_result, events)
    planner = FakePlanner(planner_result, events)
    editing = FakeEditingService(
        model_revision(extensions={}) if base_revision is None else base_revision,
        events,
    )
    authorization_gateway = AgentAuthorizationGateway(
        editing,
        ArchitecturePlanningAuthorizationPolicy(),
        TrustedAuditIdentity(
            actor_id="architecture-planning-test",
            actor_type=AuditActorType.AGENT,
            agent_version="test-v1",
            trace_id="trace:test",
        ),
    )
    return (
        ArchitecturePlanningService(parser, planner, authorization_gateway),
        parser,
        planner,
        editing,
        events,
    )


def test_propose_orders_dependencies_and_validates_without_committing() -> None:
    record = planning_record()
    candidate = proposal(canonical_operations(record))
    planning, parser, planner, editing, events = service(candidate)

    result = planning.propose("mdl_house", "a south-facing 120 m2 house with one bedroom")

    assert isinstance(result, PlanningProposalResult)
    assert result.intent == design_intent()
    assert result.base_revision.revision_number == 4
    assert result.proposal is candidate
    assert result.has_changes is True
    assert result.no_change is False
    assert parser.requirements == ["a south-facing 120 m2 house with one bedroom"]
    assert planner.calls == [(result.intent, result.base_revision)]
    assert editing.apply_calls == []
    assert events == ["parse", "current", "plan"]


def test_proposal_affected_entities_must_match_the_planning_record() -> None:
    record = planning_record()
    candidate = proposal(
        canonical_operations(record),
        affected_entity_ids=("rom_other",),
    )
    planning, _parser, _planner, editing, _events = service(candidate)

    with pytest.raises(PlannerContractError) as captured:
        planning.plan_and_commit("mdl_house", "valid requirement")

    assert captured.value.path == "/affected_entity_ids"
    assert captured.value.details == {
        "actual": ["rom_other"],
        "expected": ["rom_a"],
    }
    assert editing.apply_calls == []


def test_plan_and_commit_delegates_only_after_contract_validation() -> None:
    candidate = proposal(canonical_operations(planning_record()))
    planning, _parser, _planner, editing, events = service(candidate)

    result = planning.plan_and_commit("mdl_house", "valid requirement")

    assert isinstance(result, PlanningCommitResult)
    assert result.changed is True
    assert result.no_change is False
    assert result.base_revision.revision_number == 4
    assert result.revision.revision_number == 5
    assert result.proposal is candidate
    assert editing.apply_calls == [("mdl_house", candidate)]
    assert editing.audit_identities == [
        TrustedAuditIdentity(
            actor_id="architecture-planning-test",
            actor_type=AuditActorType.AGENT,
            agent_version="test-v1",
            trace_id="trace:test",
        )
    ]
    assert events == ["parse", "current", "plan", "current", "commit"]


def test_missing_extensions_allows_only_single_owned_container_creation() -> None:
    record = planning_record()
    operations = (
        *canonical_operations(record)[:2],
        PatchOperation("add", "/extensions", {PLANNING_EXTENSION_KEY: record.to_dict()}),
    )
    planning, _parser, _planner, _editing, _events = service(
        proposal(operations),
        base_revision=model_revision(),
    )

    assert planning.propose("mdl_house", "valid requirement").has_changes is True


def test_plan_and_commit_returns_explicit_verified_no_change() -> None:
    record = planning_record()
    base = model_revision(
        room_name="Bedroom 1",
        room_usage="bedroom",
        extensions={PLANNING_EXTENSION_KEY: record.to_dict()},
    )
    planning, _parser, _planner, editing, events = service(None, base_revision=base)

    result = planning.plan_and_commit("mdl_house", "already realized requirement")

    assert result.changed is False
    assert result.no_change is True
    assert result.proposal is None
    assert result.revision is result.base_revision
    assert result.revision.revision_number == 4
    assert editing.apply_calls == []
    assert events == ["parse", "current", "plan", "current"]


def test_no_change_result_rechecks_head_and_rejects_a_concurrent_revision() -> None:
    record = planning_record()
    base = model_revision(
        room_name="Bedroom 1",
        room_usage="bedroom",
        extensions={PLANNING_EXTENSION_KEY: record.to_dict()},
    )
    events: list[str] = []
    parser = FakeParser(design_intent(), events)
    editing = FakeEditingService(base, events)

    class AdvancingPlanner(FakePlanner):
        def plan(
            self,
            intent: DesignIntent,
            base_revision: ModelRevision,
        ) -> PatchProposal | None:
            result = super().plan(intent, base_revision)
            editing.base_revision = model_revision(
                revision_number=5,
                room_name="Bedroom 1",
                room_usage="bedroom",
                extensions={PLANNING_EXTENSION_KEY: record.to_dict()},
            )
            return result

    authorization_gateway = AgentAuthorizationGateway(
        editing,
        ArchitecturePlanningAuthorizationPolicy(),
        TrustedAuditIdentity(
            actor_id="architecture-planning-test",
            actor_type=AuditActorType.AGENT,
            agent_version="test-v1",
            trace_id="trace:test",
        ),
    )
    planning = ArchitecturePlanningService(
        parser,
        AdvancingPlanner(None, events),
        authorization_gateway,
    )

    with pytest.raises(RevisionConflictError) as error:
        planning.plan_and_commit("mdl_house", "already realized requirement")

    assert error.value.details == {"model_id": "mdl_house", "expected": 4, "actual": 5}
    assert events == ["parse", "current", "plan", "current"]
    assert editing.apply_calls == []


@pytest.mark.parametrize(
    "base",
    [
        model_revision(extensions={}),
        model_revision(
            room_name="Room A",
            room_usage="bedroom",
            extensions={PLANNING_EXTENSION_KEY: planning_record().to_dict()},
        ),
    ],
    ids=["missing-record", "room-semantics-differ"],
)
def test_false_no_change_is_rejected_before_commit(base: ModelRevision) -> None:
    planning, _parser, _planner, editing, _events = service(None, base_revision=base)

    with pytest.raises(PlannerContractError) as error:
        planning.plan_and_commit("mdl_house", "not actually realized")

    assert error.value.details["reason"] in {"MISSING_PLANNING_RECORD", "FALSE_NO_CHANGE"}
    assert editing.apply_calls == []


def test_wrong_base_revision_is_rejected_before_commit() -> None:
    candidate = proposal(canonical_operations(planning_record()), base_revision=3)
    planning, _parser, _planner, editing, _events = service(candidate)

    with pytest.raises(PlannerContractError) as error:
        planning.plan_and_commit("mdl_house", "stale plan")

    assert error.value.path == "/base_revision"
    assert error.value.details == {"actual": 3, "expected": 4}
    assert editing.apply_calls == []


def test_wrong_base_model_is_rejected_before_commit() -> None:
    candidate = proposal(
        canonical_operations(planning_record()),
        base_model_id="mdl_other",
    )
    planning, _parser, _planner, editing, _events = service(candidate)

    with pytest.raises(PlannerContractError) as error:
        planning.plan_and_commit("mdl_house", "cross-model plan")

    assert error.value.path == "/base_model_id"
    assert error.value.details == {"actual": "mdl_other", "expected": "mdl_house"}
    assert editing.apply_calls == []


@pytest.mark.parametrize(
    "operations",
    [
        (PatchOperation("remove", PLANNING_PATH),),
        (
            PatchOperation("replace", "/entities/rooms/rom_a/geometry", {}),
            PatchOperation("add", PLANNING_PATH, planning_record().to_dict()),
        ),
        (
            PatchOperation("replace", "/model_id", "mdl_owned"),
            PatchOperation("add", PLANNING_PATH, planning_record().to_dict()),
        ),
        (
            PatchOperation("add", "/metadata/planner", True),
            PatchOperation("add", PLANNING_PATH, planning_record().to_dict()),
        ),
        (
            PatchOperation("replace", "/entities/rooms/rom_a/name", "Malicious"),
            PatchOperation("add", PLANNING_PATH, planning_record().to_dict()),
        ),
        (
            PatchOperation("replace", "/entities/rooms/rom_missing/name", "Bedroom 1"),
            PatchOperation("add", PLANNING_PATH, planning_record().to_dict()),
        ),
        (
            PatchOperation(
                "add",
                "/extensions",
                {
                    PLANNING_EXTENSION_KEY: planning_record().to_dict(),
                    "evil.example.payload": {"owned": False},
                },
            ),
        ),
        (
            PatchOperation("replace", "/entities/rooms/rom_a/name", "Bedroom 1"),
            PatchOperation("add", "/entities/rooms/rom_a/usage", "bedroom"),
            PatchOperation("add", PLANNING_PATH, planning_record().to_dict()),
        ),
    ],
    ids=[
        "remove",
        "geometry",
        "identity",
        "unknown-path",
        "wrong-room-value",
        "unknown-room",
        "foreign-extension",
        "wrong-order",
    ],
)
def test_malicious_or_noncanonical_operations_are_rejected(
    operations: tuple[PatchOperation, ...],
) -> None:
    planning, _parser, _planner, editing, _events = service(proposal(operations))

    with pytest.raises(PlannerContractError):
        planning.plan_and_commit("mdl_house", "malicious proposal")

    assert editing.apply_calls == []


def test_planning_record_must_match_parsed_intent() -> None:
    other_record = planning_record(intent=design_intent(area=140))
    candidate = proposal(canonical_operations(other_record))
    planning, _parser, _planner, editing, _events = service(candidate)

    with pytest.raises(PlannerContractError, match="does not match"):
        planning.plan_and_commit("mdl_house", "120 m2 requirement")

    assert editing.apply_calls == []


@pytest.mark.parametrize(
    "constraints",
    [
        ("area", "building_type"),
        ("building_type", "orientation"),
        ("area", "building_type", "cost", "orientation"),
    ],
    ids=["missing-orientation", "missing-area", "unknown-constraint"],
)
def test_planning_record_must_disclose_exact_unverified_constraints(
    constraints: tuple[str, ...],
) -> None:
    record_value = planning_record().to_dict()
    realization = cast(dict[str, Any], record_value["realization"])
    realization["unverified_constraints"] = list(constraints)
    candidate = proposal(
        (
            PatchOperation("add", "/entities/rooms/rom_a/usage", "bedroom"),
            PatchOperation("replace", "/entities/rooms/rom_a/name", "Bedroom 1"),
            PatchOperation("add", PLANNING_PATH, record_value),
        )
    )
    planning, _parser, _planner, editing, _events = service(candidate)

    with pytest.raises(PlannerContractError) as error:
        planning.plan_and_commit("mdl_house", "unverified constraints are incomplete")

    assert error.value.details["cause"] == "INVALID_DESIGN_INTENT"
    assert editing.apply_calls == []


def test_orientation_is_unverified_only_when_the_intent_has_one() -> None:
    intent = design_intent(orientation=None)
    record = planning_record(intent=intent)
    candidate = proposal(canonical_operations(record))
    planning, _parser, _planner, _editing, _events = service(
        candidate,
        parser_result=intent,
    )

    result = planning.propose("mdl_house", "house without an orientation constraint")

    assert result.intent.orientation is None
    assert record.unverified_constraints == ("area", "building_type")


def test_redundant_proposal_must_be_reported_as_no_change() -> None:
    record = planning_record()
    base = model_revision(
        room_name="Bedroom 1",
        room_usage="bedroom",
        extensions={PLANNING_EXTENSION_KEY: record.to_dict()},
    )
    candidate = proposal((PatchOperation("replace", PLANNING_PATH, record.to_dict()),))
    planning, _parser, _planner, editing, _events = service(candidate, base_revision=base)

    with pytest.raises(PlannerContractError) as error:
        planning.plan_and_commit("mdl_house", "already realized")

    assert error.value.details == {"reason": "NO_CHANGE_EXPECTED"}
    assert editing.apply_calls == []


@pytest.mark.parametrize("planner_result", [{"operations": []}, object()])
def test_non_patch_planner_results_are_rejected(planner_result: object) -> None:
    planning, _parser, _planner, editing, _events = service(planner_result)

    with pytest.raises(PlannerContractError) as error:
        planning.plan_and_commit("mdl_house", "malformed proposal")

    assert error.value.path == "/proposal"
    assert editing.apply_calls == []


def test_incompletely_initialized_patch_proposal_is_rejected() -> None:
    malformed = object.__new__(PatchProposal)
    planning, _parser, _planner, editing, _events = service(malformed)

    with pytest.raises(PlannerContractError) as error:
        planning.plan_and_commit("mdl_house", "malformed proposal")

    assert error.value.path == "/proposal"
    assert editing.apply_calls == []


def test_parser_contract_is_checked_before_reading_model() -> None:
    planning, _parser, _planner, editing, events = service(
        None,
        parser_result=cast(Any, {"rooms": ["bedroom"]}),
    )

    with pytest.raises(PlannerContractError) as error:
        planning.propose("mdl_house", "bad parser result")

    assert error.value.path == "/intent"
    assert editing.apply_calls == []
    assert events == ["parse"]
