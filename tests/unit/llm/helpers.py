from __future__ import annotations

from datetime import UTC, datetime

from ai_parametric_architect.domain import (
    DesignIntent,
    ModelRevision,
    PatchOperation,
    PatchProposal,
)
from ai_parametric_architect.planning import FloorPlanProposal, RuleBasedFloorPlanPlanner


def make_intent() -> DesignIntent:
    return DesignIntent(
        building_type="house",
        area=120,
        rooms=("living", "bedroom"),
        orientation="south",
    )


def make_plan() -> FloorPlanProposal:
    return RuleBasedFloorPlanPlanner().plan(make_intent())


def make_revision() -> ModelRevision:
    return ModelRevision(
        model_id="mdl_llm",
        revision_number=2,
        created_at=datetime(2026, 7, 15, 12, tzinfo=UTC),
        parent_revision=1,
        document={
            "model_id": "mdl_llm",
            "revision": 2,
            "entities": {
                "rooms": {
                    "rom_living": {"id": "rom_living", "entity_type": "room"},
                    "rom_bedroom": {"id": "rom_bedroom", "entity_type": "room"},
                }
            },
        },
    )


def make_patch() -> PatchProposal:
    return PatchProposal(
        base_model_id="mdl_llm",
        base_revision=2,
        operations=(
            PatchOperation(
                "replace",
                "/entities/rooms/rom_living/name",
                "Living",
            ),
        ),
        provenance="llm:mock-llm-provider",
        rationale="Apply the detached floor-plan suggestion.",
        affected_entity_ids=("rom_living",),
    )
