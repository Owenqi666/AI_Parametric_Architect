"""Validated detached-patch success metric."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from ai_parametric_architect.evaluation.metrics.models import MetricResult, summarize_binary

PATCH_VALIDATION_SUCCESS_RATE: Final = "patch_validation_success_rate"


@dataclass(frozen=True, slots=True)
class PatchValidationSuccessRate:
    """Aggregate whether generated patches pass the injected core validator."""

    def summarize(self, observations: Iterable[bool]) -> MetricResult:
        return summarize_binary(PATCH_VALIDATION_SUCCESS_RATE, observations)
