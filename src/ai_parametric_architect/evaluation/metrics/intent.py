"""Exact DesignIntent extraction accuracy."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.evaluation.metrics.models import MetricResult, summarize_binary
from ai_parametric_architect.evaluation.scenarios import Scenario

INTENT_EXTRACTION_ACCURACY: Final = "intent_extraction_accuracy"


@dataclass(frozen=True, slots=True)
class IntentExtractionAccuracy:
    """Score exact, provider-neutral DesignIntent equality per scenario."""

    def matches(self, actual: DesignIntent, scenario: Scenario) -> bool:
        return actual == scenario.expected_intent

    def summarize(self, observations: Iterable[bool]) -> MetricResult:
        return summarize_binary(INTENT_EXTRACTION_ACCURACY, observations)
