"""Provider-neutral port for converting a detached Plan IR into a patch proposal."""

from __future__ import annotations

from typing import Protocol, TypeVar

from ai_parametric_architect.domain.patches import PatchProposal
from ai_parametric_architect.domain.revisions import ModelRevision

PlanT = TypeVar("PlanT", contravariant=True)


class PatchProposalGenerator(Protocol[PlanT]):
    """Generate a proposed change without applying or committing it."""

    def generate(
        self,
        plan: PlanT,
        current_revision: ModelRevision,
    ) -> PatchProposal | None: ...
