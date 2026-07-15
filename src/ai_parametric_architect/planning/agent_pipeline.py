"""Provider-neutral orchestration from design intent to detached patch proposal."""

from __future__ import annotations

from dataclasses import dataclass, field

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.patches import PatchProposal
from ai_parametric_architect.domain.planning_errors import (
    PlannerContractError,
    PlanningContextError,
)
from ai_parametric_architect.domain.revisions import ModelRevision
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.ports.patch_generation import PatchProposalGenerator
from ai_parametric_architect.ports.planning import FloorPlanPlanner


@dataclass(frozen=True, slots=True)
class AgentPlanningPipeline:
    """Sequence Plan IR creation and patch proposal generation without side effects."""

    _floor_plan_planner: FloorPlanPlanner[FloorPlanProposal] = field(repr=False)
    _patch_generator: PatchProposalGenerator[FloorPlanProposal] = field(repr=False)

    def plan(
        self,
        intent: DesignIntent,
        base_revision: ModelRevision,
    ) -> PatchProposal | None:
        if not isinstance(intent, DesignIntent):
            raise PlanningContextError(
                "Agent planning requires a validated DesignIntent.",
                path="/intent",
                details={"reason": "INVALID_INTENT_TYPE"},
            )
        if not isinstance(base_revision, ModelRevision):
            raise PlanningContextError(
                "Agent planning requires a ModelRevision context.",
                path="/base_revision",
                details={"reason": "INVALID_REVISION_TYPE"},
            )

        floor_plan = self._floor_plan_planner.plan(intent)
        if not isinstance(floor_plan, FloorPlanProposal):
            raise PlannerContractError(
                "Floor-plan planner returned a value that is not a FloorPlanProposal.",
                path="/floor_plan",
                details={
                    "actual_type": type(floor_plan).__name__,
                    "expected_type": "FloorPlanProposal",
                },
            )
        if floor_plan.intent != intent:
            raise PlannerContractError(
                "Floor-plan proposal does not retain the input DesignIntent.",
                path="/floor_plan/intent",
                details={"reason": "INTENT_MISMATCH"},
            )

        result = self._patch_generator.generate(floor_plan, base_revision)
        if result is not None:
            if type(result) is not PatchProposal:
                raise PlannerContractError(
                    "Patch generator returned a value that is not a PatchProposal.",
                    path="/patch_proposal",
                    details={
                        "actual_type": type(result).__name__,
                        "expected_type": "PatchProposal or None",
                    },
                )
            if result.base_model_id != base_revision.model_id:
                raise PlannerContractError(
                    "Patch proposal is bound to a different model.",
                    path="/patch_proposal/base_model_id",
                    details={
                        "actual": result.base_model_id,
                        "expected": base_revision.model_id,
                    },
                )
            if result.base_revision != base_revision.revision_number:
                raise PlannerContractError(
                    "Patch proposal is bound to a different revision.",
                    path="/patch_proposal/base_revision",
                    details={
                        "actual": result.base_revision,
                        "expected": base_revision.revision_number,
                    },
                )
        return result
