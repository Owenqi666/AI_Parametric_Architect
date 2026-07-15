from __future__ import annotations

import json
from collections import Counter

from ai_parametric_architect.planning import CP_SAT_STRATEGY
from ai_parametric_architect.showcase import (
    SHOWCASE_ARTIFACT_KIND,
    SHOWCASE_EXECUTION_MODE,
    ShowcaseStatus,
    canonical_proposal_digest,
)
from ai_parametric_architect.showcase_generation import (
    COMPACT_APARTMENT_REQUIREMENT,
    CONSTRAINT_CONFLICT_REQUIREMENT,
    FAMILY_HOUSE_REQUIREMENT,
    RECORDED_MOCK_INTENT_PARSER_NAME,
    SHOWCASE_INTENTS,
    build_preview_artifact,
)


def test_showcase_has_two_solved_previews_and_one_fail_closed_case() -> None:
    artifact = build_preview_artifact()

    assert artifact.artifact_kind == SHOWCASE_ARTIFACT_KIND
    assert artifact.execution.mode == SHOWCASE_EXECUTION_MODE
    assert artifact.execution.planner_strategy == CP_SAT_STRATEGY
    assert artifact.execution.intent_agent_name == RECORDED_MOCK_INTENT_PARSER_NAME
    assert "recorded" in artifact.execution.intent_agent_name
    assert "mock" in artifact.execution.intent_agent_name
    assert "openai" not in artifact.execution.intent_agent_name.lower()
    assert tuple(value.scenario_id for value in artifact.scenarios) == (
        "family-house",
        "compact-apartment",
        "constraint-conflict",
    )
    family, compact, conflict = artifact.scenarios
    assert family.input_requirement == FAMILY_HOUSE_REQUIREMENT
    assert compact.input_requirement == COMPACT_APARTMENT_REQUIREMENT
    assert conflict.input_requirement == CONSTRAINT_CONFLICT_REQUIREMENT
    assert family.status is ShowcaseStatus.SUCCESS
    assert compact.status is ShowcaseStatus.SUCCESS
    assert family.intent == SHOWCASE_INTENTS[0]
    assert compact.intent == SHOWCASE_INTENTS[1]
    assert family.proposal is not None
    assert compact.proposal is not None
    assert family.proposal_digest == canonical_proposal_digest(family.proposal)
    assert compact.proposal_digest == canonical_proposal_digest(compact.proposal)
    assert conflict.status is ShowcaseStatus.REJECTED
    assert conflict.intent is None
    assert conflict.proposal is None
    assert conflict.proposal_digest is None
    assert conflict.evidence is None
    assert conflict.failure is not None
    assert conflict.failure.to_dict() == {
        "stage": "plan",
        "code": "PLANNING_SOLVER_FAILED",
        "path": "/problem",
    }


def test_recorded_mock_intents_exactly_preserve_requested_semantics() -> None:
    family, compact, conflict = SHOWCASE_INTENTS

    assert family.to_dict() == {
        "building_type": "house",
        "area": 120,
        "rooms": ["bedroom", "bedroom", "bedroom", "living", "kitchen"],
        "orientation": "south",
        "spatial_constraints": [
            {
                "source_room_type": "kitchen",
                "relation": "adjacent_to",
                "target_room_type": "living",
                "required": True,
            }
        ],
    }
    assert Counter(family.rooms) == Counter(
        {"bedroom": 3, "living": 1, "kitchen": 1}
    )
    assert compact.building_type == "apartment"
    assert compact.area == 72
    assert Counter(compact.rooms) == Counter(
        {"bedroom": 1, "bathroom": 1, "living": 1, "kitchen": 1}
    )
    assert compact.spatial_constraints == ()
    assert conflict.to_dict()["spatial_constraints"] == [
        {
            "source_room_type": "bedroom",
            "relation": "north_of",
            "target_room_type": "bathroom",
            "required": True,
        },
        {
            "source_room_type": "bedroom",
            "relation": "south_of",
            "target_room_type": "bathroom",
            "required": True,
        },
    ]


def test_showcase_metrics_are_real_single_proposal_evaluator_results() -> None:
    artifact = build_preview_artifact()
    family, compact, _conflict = artifact.scenarios
    assert family.evidence is not None
    assert compact.evidence is not None
    assert tuple(value.system_id for value in family.evidence.systems) == ("cp-sat-v2",)
    assert tuple(value.system_id for value in compact.evidence.systems) == (
        "rule-spatial-v2",
        "cp-sat-v2",
    )

    for scenario in (family, compact):
        assert scenario.evidence is not None
        for system in scenario.evidence.systems:
            metrics = system.to_dict()["metrics"]
            encoded = json.dumps(metrics, allow_nan=False, sort_keys=True)
            assert "runtime" not in encoded
            assert system.report.constraint_satisfaction_score.applicable
            assert system.report.spatial_efficiency_score.applicable
            assert system.report.circulation_score.applicable
            assert not system.report.plan_stability_score.applicable
            assert system.report.plan_stability_score.reason == "REPEATED_PLANS_REQUIRED"
