"""Immutable metric result values."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricResult:
    """A deterministic binary metric aggregate."""

    name: str
    successes: int
    total: int

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Metric name must be a non-empty string.")
        if (
            not isinstance(self.successes, int)
            or isinstance(self.successes, bool)
            or not isinstance(self.total, int)
            or isinstance(self.total, bool)
            or self.successes < 0
            or self.total < 0
            or self.successes > self.total
        ):
            raise ValueError("Metric counts must satisfy 0 <= successes <= total.")

    @property
    def value(self) -> float:
        return self.successes / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "successes": self.successes,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    """The required Task 6.2 metric set."""

    intent_extraction_accuracy: MetricResult
    plan_validity: MetricResult
    patch_validation_success_rate: MetricResult

    def to_dict(self) -> dict[str, object]:
        return {
            "intent_extraction_accuracy": self.intent_extraction_accuracy.to_dict(),
            "plan_validity": self.plan_validity.to_dict(),
            "patch_validation_success_rate": self.patch_validation_success_rate.to_dict(),
        }


def summarize_binary(name: str, observations: Iterable[bool]) -> MetricResult:
    values = tuple(observations)
    if not all(isinstance(value, bool) for value in values):
        raise TypeError("Binary metric observations must be booleans.")
    return MetricResult(name=name, successes=sum(values), total=len(values))
