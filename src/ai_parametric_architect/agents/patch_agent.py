"""Patch-generation agent enforcing the detached proposal contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from ai_parametric_architect.agents.requirement_agent import AgentContractError
from ai_parametric_architect.domain.patches import PatchProposal
from ai_parametric_architect.domain.revisions import ModelRevision
from ai_parametric_architect.planning.models import FloorPlanProposal
from ai_parametric_architect.ports.patch_generation import PatchProposalGenerator

PATCH_GENERATOR_AGENT_NAME: Final = "patch-generator-agent"
PATCH_GENERATOR_AGENT_VERSION: Final = "1.0.0"


@dataclass(frozen=True, slots=True)
class PatchGenerationRequest:
    """Immutable input pairing a detached plan with its exact world snapshot."""

    plan: FloorPlanProposal
    current_revision: ModelRevision


@dataclass(frozen=True, slots=True)
class PatchGeneratorAgent:
    """Convert a Plan IR into a checked proposal without touching world state."""

    _generator: PatchProposalGenerator[FloorPlanProposal] = field(repr=False)

    @property
    def name(self) -> str:
        return PATCH_GENERATOR_AGENT_NAME

    @property
    def version(self) -> str:
        return PATCH_GENERATOR_AGENT_VERSION

    def run(self, value: PatchGenerationRequest) -> PatchProposal | None:
        if not isinstance(value, PatchGenerationRequest):
            raise AgentContractError(
                "Patch generator input is not a PatchGenerationRequest.",
                path="/input",
                details={
                    "agent": self.name,
                    "actual_type": type(value).__name__,
                    "expected_type": "PatchGenerationRequest",
                },
            )
        if not isinstance(value.plan, FloorPlanProposal):
            raise AgentContractError(
                "Patch generation request plan is not a FloorPlanProposal.",
                path="/input/plan",
                details={
                    "agent": self.name,
                    "actual_type": type(value.plan).__name__,
                    "expected_type": "FloorPlanProposal",
                },
            )
        if not isinstance(value.current_revision, ModelRevision):
            raise AgentContractError(
                "Patch generation request revision is not a ModelRevision.",
                path="/input/current_revision",
                details={
                    "agent": self.name,
                    "actual_type": type(value.current_revision).__name__,
                    "expected_type": "ModelRevision",
                },
            )

        result = self._generator.generate(value.plan, value.current_revision)
        if result is None:
            return None
        if type(result) is not PatchProposal:
            raise AgentContractError(
                "Patch proposal generator returned a value that is not a PatchProposal.",
                path="/output",
                details={
                    "agent": self.name,
                    "actual_type": type(result).__name__,
                    "expected_type": "PatchProposal or None",
                },
            )
        if result.base_model_id != value.current_revision.model_id:
            raise AgentContractError(
                "Patch proposal is bound to a different model.",
                path="/output/base_model_id",
                details={
                    "agent": self.name,
                    "reason": "BASE_MODEL_MISMATCH",
                    "actual_model_id": result.base_model_id,
                    "expected_model_id": value.current_revision.model_id,
                },
            )
        if result.base_revision != value.current_revision.revision_number:
            raise AgentContractError(
                "Patch proposal is based on a different model revision.",
                path="/output/base_revision",
                details={
                    "agent": self.name,
                    "reason": "BASE_REVISION_MISMATCH",
                    "actual_revision": result.base_revision,
                    "expected_revision": value.current_revision.revision_number,
                },
            )
        if not result.affected_entity_ids:
            raise AgentContractError(
                "Patch proposal must identify at least one affected entity.",
                path="/output/affected_entity_ids",
                details={
                    "agent": self.name,
                    "reason": "AFFECTED_ENTITY_IDS_EMPTY",
                },
            )

        known_ids = _revision_entity_ids(value.current_revision, agent_name=self.name)
        unknown_ids = tuple(
            entity_id for entity_id in result.affected_entity_ids if entity_id not in known_ids
        )
        if unknown_ids:
            raise AgentContractError(
                "Patch proposal references entities absent from the current revision.",
                path="/output/affected_entity_ids",
                details={
                    "agent": self.name,
                    "reason": "UNKNOWN_AFFECTED_ENTITY_IDS",
                    "unknown_entity_ids": list(unknown_ids),
                },
            )
        return result

    def generate(
        self,
        plan: FloorPlanProposal,
        current_revision: ModelRevision,
    ) -> PatchProposal | None:
        """Implement the patch-generation port for safe pipeline composition."""

        return self.run(PatchGenerationRequest(plan=plan, current_revision=current_revision))


def _revision_entity_ids(revision: ModelRevision, *, agent_name: str) -> frozenset[str]:
    entities = revision.document.get("entities")
    if not isinstance(entities, Mapping):
        raise AgentContractError(
            "Patch generation revision has no valid entity registry.",
            path="/input/current_revision/document/entities",
            details={"agent": agent_name, "reason": "INVALID_ENTITY_REGISTRY"},
        )

    entity_ids: set[str] = set()
    for registry_name, registry in entities.items():
        if not isinstance(registry_name, str) or not isinstance(registry, Mapping):
            raise AgentContractError(
                "Patch generation revision has a malformed entity registry.",
                path="/input/current_revision/document/entities",
                details={"agent": agent_name, "reason": "INVALID_ENTITY_REGISTRY"},
            )
        for entity_id in registry:
            if not isinstance(entity_id, str) or not entity_id:
                raise AgentContractError(
                    "Patch generation revision has a malformed entity ID.",
                    path=f"/input/current_revision/document/entities/{_pointer_token(registry_name)}",
                    details={"agent": agent_name, "reason": "INVALID_ENTITY_ID"},
                )
            entity_ids.add(entity_id)
    return frozenset(entity_ids)


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")
