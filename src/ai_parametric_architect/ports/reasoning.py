"""Provider-neutral port for symbolic validation-constraint reasoning."""

from __future__ import annotations

from typing import Protocol, TypeVar

from ai_parametric_architect.domain.issues import ValidationIssue

ResolutionPlanT = TypeVar("ResolutionPlanT", covariant=True)


class ConstraintSolver(Protocol[ResolutionPlanT]):
    def solve(self, issue: ValidationIssue) -> ResolutionPlanT: ...
