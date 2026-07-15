"""Immutable, allowlist-only values for detached planning benchmarks."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from ai_parametric_architect.evaluation.planning_metrics.models import PlanningMetricContext

BENCHMARK_REPORT_SCHEMA_VERSION: Final = "1.0.0"
NO_APPLICABLE_SAMPLES: Final = "NO_APPLICABLE_SAMPLES"
NO_RUNTIME_SAMPLES: Final = "NO_RUNTIME_SAMPLES"

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.:-]*$")
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BenchmarkExecutionMode(StrEnum):
    """Whether a benchmark system is reproducible or calls a real stochastic service."""

    DETERMINISTIC = "deterministic"
    REAL_NONDETERMINISTIC = "real_nondeterministic"


class BenchmarkTrack(StrEnum):
    END_TO_END = "end_to_end"
    ORACLE_INTENT = "oracle_intent"


class BenchmarkStage(StrEnum):
    INTENT = "intent"
    PLAN = "plan"


@dataclass(frozen=True, slots=True)
class BenchmarkSystemDescriptor:
    """Serializable identity for one injected parser/planner combination."""

    system_id: str
    system_version: str
    intent_agent_name: str
    intent_agent_version: str
    floor_plan_agent_name: str
    floor_plan_agent_version: str
    planner_strategy: str
    rules_version: str
    random_seed: int | None
    execution_mode: BenchmarkExecutionMode
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.system_id, "system_id")
        for required_name, required_value in (
            ("system_version", self.system_version),
            ("intent_agent_name", self.intent_agent_name),
            ("intent_agent_version", self.intent_agent_version),
            ("floor_plan_agent_name", self.floor_plan_agent_name),
            ("floor_plan_agent_version", self.floor_plan_agent_version),
            ("planner_strategy", self.planner_strategy),
            ("rules_version", self.rules_version),
        ):
            _require_text(required_value, required_name)
        if not isinstance(self.execution_mode, BenchmarkExecutionMode):
            raise TypeError("execution_mode must be a BenchmarkExecutionMode.")
        optional_metadata: tuple[tuple[str, str | None], ...] = (
            ("provider", self.provider),
            ("model", self.model),
            ("prompt_version", self.prompt_version),
        )
        for optional_name, optional_value in optional_metadata:
            if optional_value is not None:
                _require_text(optional_value, optional_name)
        if self.execution_mode is BenchmarkExecutionMode.REAL_NONDETERMINISTIC and (
            self.provider is None or self.model is None
        ):
            raise ValueError("Real nondeterministic systems must identify provider and model.")
        if self.random_seed is None:
            if self.execution_mode is BenchmarkExecutionMode.DETERMINISTIC:
                raise ValueError("Deterministic systems must declare a random seed.")
        else:
            _require_nonnegative_int(self.random_seed, "random_seed")

    @property
    def deterministic(self) -> bool:
        return self.execution_mode is BenchmarkExecutionMode.DETERMINISTIC

    def to_dict(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "system_version": self.system_version,
            "intent_agent": {
                "name": self.intent_agent_name,
                "version": self.intent_agent_version,
            },
            "floor_plan_agent": {
                "name": self.floor_plan_agent_name,
                "version": self.floor_plan_agent_version,
            },
            "planner_configuration": {
                "strategy": self.planner_strategy,
                "rules_version": self.rules_version,
                "random_seed": self.random_seed,
            },
            "execution_mode": self.execution_mode.value,
            "deterministic": self.deterministic,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkBudget:
    """Hard preflight limits; one attempt is one system/case/trial tuple."""

    max_cases: int = 256
    max_systems: int = 8
    max_trials: int = 64
    max_attempts: int = 4096

    def __post_init__(self) -> None:
        for name, value in (
            ("max_cases", self.max_cases),
            ("max_systems", self.max_systems),
            ("max_trials", self.max_trials),
            ("max_attempts", self.max_attempts),
        ):
            _require_positive_int(value, name)

    def require(self, *, case_count: int, system_count: int, trials: int) -> int:
        """Validate the complete run before any agent or clock is called."""

        _require_positive_int(case_count, "case_count")
        _require_positive_int(system_count, "system_count")
        _require_positive_int(trials, "trials")
        if case_count > self.max_cases:
            raise ValueError("Benchmark case count exceeds the configured budget.")
        if system_count > self.max_systems:
            raise ValueError("Benchmark system count exceeds the configured budget.")
        if trials > self.max_trials:
            raise ValueError("Benchmark trial count exceeds the configured budget.")
        attempt_count = case_count * system_count * trials
        if attempt_count > self.max_attempts:
            raise ValueError("Benchmark attempt count exceeds the configured budget.")
        return attempt_count

    def to_dict(self) -> dict[str, int]:
        return {
            "max_cases": self.max_cases,
            "max_systems": self.max_systems,
            "max_trials": self.max_trials,
            "max_attempts": self.max_attempts,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkFailure:
    """A deliberately redacted known failure: no message, details, or provider payload."""

    stage: BenchmarkStage
    code: str
    path: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.stage, BenchmarkStage):
            raise TypeError("stage must be a BenchmarkStage.")
        if not isinstance(self.code, str) or _ERROR_CODE.fullmatch(self.code) is None:
            raise ValueError("Benchmark failure code must be canonical.")
        if not isinstance(self.path, str) or (self.path and not self.path.startswith("/")):
            raise ValueError("Benchmark failure path must be empty or a JSON pointer.")

    def to_dict(self) -> dict[str, str]:
        return {"stage": self.stage.value, "code": self.code, "path": self.path}


@dataclass(frozen=True, slots=True)
class BenchmarkTrackObservation:
    """Allowlisted outcome for one track; detached typed values are never retained."""

    track: BenchmarkTrack
    planning_succeeded: bool
    plan_valid: bool
    proposal_digest: str | None
    parse_runtime_ns: int | None
    plan_runtime_ns: int | None
    total_runtime_ns: int
    failure: BenchmarkFailure | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.track, BenchmarkTrack):
            raise TypeError("track must be a BenchmarkTrack.")
        for name, value in (
            ("planning_succeeded", self.planning_succeeded),
            ("plan_valid", self.plan_valid),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a boolean.")
        if self.plan_valid and not self.planning_succeeded:
            raise ValueError("A valid plan requires successful planning.")
        if self.planning_succeeded:
            _require_digest(self.proposal_digest, "proposal_digest")
            if self.failure is not None:
                raise ValueError("A successful plan cannot retain a failure.")
        elif self.proposal_digest is not None:
            raise ValueError("A failed plan cannot retain a proposal digest.")
        if self.failure is not None and not isinstance(self.failure, BenchmarkFailure):
            raise TypeError("failure must be a BenchmarkFailure.")
        if self.track is BenchmarkTrack.END_TO_END:
            _require_nonnegative_int(self.parse_runtime_ns, "parse_runtime_ns")
        elif self.parse_runtime_ns is not None:
            raise ValueError("Oracle-intent observations do not run an intent parser.")
        if self.plan_runtime_ns is not None:
            _require_nonnegative_int(self.plan_runtime_ns, "plan_runtime_ns")
        _require_nonnegative_int(self.total_runtime_ns, "total_runtime_ns")
        expected_total = (self.parse_runtime_ns or 0) + (self.plan_runtime_ns or 0)
        if self.total_runtime_ns != expected_total:
            raise ValueError("Track total runtime must equal its measured stage runtimes.")
        if self.planning_succeeded and self.plan_runtime_ns is None:
            raise ValueError("Successful planning requires a measured plan runtime.")
        if self.failure is not None:
            if self.failure.stage is BenchmarkStage.INTENT and self.plan_runtime_ns is not None:
                raise ValueError("Planning cannot run after an intent-stage failure.")
            if self.failure.stage is BenchmarkStage.PLAN and self.plan_runtime_ns is None:
                raise ValueError("Plan-stage failures require a measured plan runtime.")

    def to_dict(self) -> dict[str, object]:
        return {
            "track": self.track.value,
            "planning_succeeded": self.planning_succeeded,
            "plan_valid": self.plan_valid,
            "proposal_digest": self.proposal_digest,
            "runtime_ns": {
                "parse": self.parse_runtime_ns,
                "plan": self.plan_runtime_ns,
                "total": self.total_runtime_ns,
            },
            "failure": None if self.failure is None else self.failure.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class BenchmarkAttemptObservation:
    case_id: str
    system_id: str
    trial_index: int
    intent_exact: bool
    end_to_end: BenchmarkTrackObservation
    oracle_intent: BenchmarkTrackObservation

    def __post_init__(self) -> None:
        _require_identifier(self.case_id, "case_id")
        _require_identifier(self.system_id, "system_id")
        _require_nonnegative_int(self.trial_index, "trial_index")
        if not isinstance(self.intent_exact, bool):
            raise TypeError("intent_exact must be a boolean.")
        if self.end_to_end.track is not BenchmarkTrack.END_TO_END:
            raise ValueError("end_to_end must contain the end-to-end track.")
        if self.oracle_intent.track is not BenchmarkTrack.ORACLE_INTENT:
            raise ValueError("oracle_intent must contain the oracle-intent track.")

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "system_id": self.system_id,
            "trial_index": self.trial_index,
            "intent_exact": self.intent_exact,
            "tracks": {
                BenchmarkTrack.END_TO_END.value: self.end_to_end.to_dict(),
                BenchmarkTrack.ORACLE_INTENT.value: self.oracle_intent.to_dict(),
            },
        }


@dataclass(frozen=True, slots=True)
class BenchmarkMetricSummary:
    """Normalized score plus explicit attempt and applicability coverage."""

    name: str
    value: float | None
    attempt_count: int
    covered_attempt_count: int
    sample_count: int
    successes: int | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.name, "name")
        _require_positive_int(self.attempt_count, "attempt_count")
        _require_nonnegative_int(self.covered_attempt_count, "covered_attempt_count")
        _require_nonnegative_int(self.sample_count, "sample_count")
        if self.covered_attempt_count > self.attempt_count:
            raise ValueError("Metric coverage cannot exceed attempt count.")
        if self.value is None:
            if self.covered_attempt_count != 0 or self.sample_count != 0:
                raise ValueError("A non-applicable metric cannot contain samples.")
            if not isinstance(self.reason, str) or not self.reason:
                raise ValueError("A non-applicable metric requires a reason.")
            if self.successes is not None:
                raise ValueError("A non-applicable metric cannot contain successes.")
            return
        value = _normalized_float(self.value, "value")
        object.__setattr__(self, "value", value)
        if self.sample_count < 1 or self.covered_attempt_count < 1 or self.reason is not None:
            raise ValueError("An applicable metric requires covered samples and no reason.")
        if self.successes is not None:
            _require_nonnegative_int(self.successes, "successes")
            if self.successes > self.sample_count:
                raise ValueError("Metric successes cannot exceed sample count.")

    @property
    def applicable(self) -> bool:
        return self.value is not None

    @property
    def coverage(self) -> float:
        return self.covered_attempt_count / self.attempt_count

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "applicable": self.applicable,
            "attempt_count": self.attempt_count,
            "covered_attempt_count": self.covered_attempt_count,
            "sample_count": self.sample_count,
            "coverage": self.coverage,
            "successes": self.successes,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkRuntimeSummary:
    """Integer nanosecond summary using nearest-rank median and p95."""

    name: str
    attempt_count: int
    covered_attempt_count: int
    sample_count: int
    minimum_ns: int | None
    median_ns: int | None
    p95_ns: int | None
    maximum_ns: int | None
    total_ns: int | None
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.name, "name")
        _require_positive_int(self.attempt_count, "attempt_count")
        _require_nonnegative_int(self.covered_attempt_count, "covered_attempt_count")
        _require_nonnegative_int(self.sample_count, "sample_count")
        if self.covered_attempt_count > self.attempt_count:
            raise ValueError("Runtime coverage cannot exceed attempt count.")
        values = (self.minimum_ns, self.median_ns, self.p95_ns, self.maximum_ns, self.total_ns)
        if self.sample_count == 0:
            if self.covered_attempt_count != 0 or any(value is not None for value in values):
                raise ValueError("A runtime without samples cannot contain values.")
            if not isinstance(self.reason, str) or not self.reason:
                raise ValueError("A runtime without samples requires a reason.")
            return
        if self.covered_attempt_count < 1 or self.reason is not None:
            raise ValueError("A sampled runtime requires coverage and no reason.")
        for name, value in zip(
            ("minimum_ns", "median_ns", "p95_ns", "maximum_ns", "total_ns"),
            values,
            strict=True,
        ):
            _require_nonnegative_int(value, name)
        assert self.minimum_ns is not None
        assert self.median_ns is not None
        assert self.p95_ns is not None
        assert self.maximum_ns is not None
        assert self.total_ns is not None
        if not self.minimum_ns <= self.median_ns <= self.p95_ns <= self.maximum_ns:
            raise ValueError("Runtime quantiles must be ordered.")
        if self.total_ns < self.maximum_ns:
            raise ValueError("Runtime total cannot be smaller than its maximum sample.")

    @property
    def applicable(self) -> bool:
        return self.sample_count > 0

    @property
    def coverage(self) -> float:
        return self.covered_attempt_count / self.attempt_count

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "applicable": self.applicable,
            "attempt_count": self.attempt_count,
            "covered_attempt_count": self.covered_attempt_count,
            "sample_count": self.sample_count,
            "coverage": self.coverage,
            "minimum_ns": self.minimum_ns,
            "median_ns": self.median_ns,
            "p95_ns": self.p95_ns,
            "maximum_ns": self.maximum_ns,
            "total_ns": self.total_ns,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkTrackSummary:
    track: BenchmarkTrack
    planning_success: BenchmarkMetricSummary
    plan_validity: BenchmarkMetricSummary
    constraint_satisfaction: BenchmarkMetricSummary
    spatial_efficiency: BenchmarkMetricSummary
    circulation: BenchmarkMetricSummary
    stability: BenchmarkMetricSummary
    parse_runtime: BenchmarkRuntimeSummary
    plan_runtime: BenchmarkRuntimeSummary
    total_runtime: BenchmarkRuntimeSummary

    def __post_init__(self) -> None:
        if not isinstance(self.track, BenchmarkTrack):
            raise TypeError("track must be a BenchmarkTrack.")
        metrics = (
            self.planning_success,
            self.plan_validity,
            self.constraint_satisfaction,
            self.spatial_efficiency,
            self.circulation,
            self.stability,
        )
        runtimes = (self.parse_runtime, self.plan_runtime, self.total_runtime)
        if not all(isinstance(metric, BenchmarkMetricSummary) for metric in metrics):
            raise TypeError("Track metrics must be BenchmarkMetricSummary values.")
        if not all(isinstance(runtime, BenchmarkRuntimeSummary) for runtime in runtimes):
            raise TypeError("Track runtimes must be BenchmarkRuntimeSummary values.")
        attempt_counts = {value.attempt_count for value in (*metrics, *runtimes)}
        if len(attempt_counts) != 1:
            raise ValueError("Every track summary must use the same attempt denominator.")

    def to_dict(self) -> dict[str, object]:
        return {
            "track": self.track.value,
            "metrics": {
                "planning_success": self.planning_success.to_dict(),
                "plan_validity": self.plan_validity.to_dict(),
                "constraint_satisfaction": self.constraint_satisfaction.to_dict(),
                "spatial_efficiency": self.spatial_efficiency.to_dict(),
                "circulation": self.circulation.to_dict(),
                "stability": self.stability.to_dict(),
            },
            "runtime_ns": {
                "parse": self.parse_runtime.to_dict(),
                "plan": self.plan_runtime.to_dict(),
                "total": self.total_runtime.to_dict(),
            },
        }


@dataclass(frozen=True, slots=True)
class BenchmarkSystemReport:
    descriptor: BenchmarkSystemDescriptor
    attempt_count: int
    intent_extraction_accuracy: BenchmarkMetricSummary
    end_to_end: BenchmarkTrackSummary
    oracle_intent: BenchmarkTrackSummary

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, BenchmarkSystemDescriptor):
            raise TypeError("descriptor must be a BenchmarkSystemDescriptor.")
        _require_positive_int(self.attempt_count, "attempt_count")
        if self.intent_extraction_accuracy.attempt_count != self.attempt_count:
            raise ValueError("Intent accuracy must use every benchmark attempt.")
        if self.end_to_end.track is not BenchmarkTrack.END_TO_END:
            raise ValueError("end_to_end must summarize the end-to-end track.")
        if self.oracle_intent.track is not BenchmarkTrack.ORACLE_INTENT:
            raise ValueError("oracle_intent must summarize the oracle-intent track.")
        if (
            self.end_to_end.planning_success.attempt_count != self.attempt_count
            or self.oracle_intent.planning_success.attempt_count != self.attempt_count
        ):
            raise ValueError("Track summaries must use every benchmark attempt.")

    def to_dict(self) -> dict[str, object]:
        return {
            "descriptor": self.descriptor.to_dict(),
            "attempt_count": self.attempt_count,
            "intent_extraction_accuracy": self.intent_extraction_accuracy.to_dict(),
            "tracks": {
                BenchmarkTrack.END_TO_END.value: self.end_to_end.to_dict(),
                BenchmarkTrack.ORACLE_INTENT.value: self.oracle_intent.to_dict(),
            },
        }


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Detached derived evidence; intentionally contains no requirement or typed output."""

    dataset_id: str
    dataset_version: str
    dataset_digest: str
    annotation_set_id: str
    annotation_set_version: str
    annotation_digest: str
    case_count: int
    trials: int
    budget: BenchmarkBudget
    metric_context: PlanningMetricContext
    systems: tuple[BenchmarkSystemReport, ...]
    observations: tuple[BenchmarkAttemptObservation, ...]
    schema_version: str = BENCHMARK_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BENCHMARK_REPORT_SCHEMA_VERSION:
            raise ValueError("Unsupported benchmark report schema version.")
        _require_identifier(self.dataset_id, "dataset_id")
        _require_text(self.dataset_version, "dataset_version")
        _require_digest(self.dataset_digest, "dataset_digest")
        _require_identifier(self.annotation_set_id, "annotation_set_id")
        _require_text(self.annotation_set_version, "annotation_set_version")
        _require_digest(self.annotation_digest, "annotation_digest")
        _require_positive_int(self.case_count, "case_count")
        _require_positive_int(self.trials, "trials")
        if not isinstance(self.budget, BenchmarkBudget):
            raise TypeError("budget must be a BenchmarkBudget.")
        if not isinstance(self.metric_context, PlanningMetricContext):
            raise TypeError("metric_context must be a PlanningMetricContext.")
        if not self.systems or not all(
            isinstance(system, BenchmarkSystemReport) for system in self.systems
        ):
            raise ValueError("Benchmark report requires system summaries.")
        system_ids = tuple(system.descriptor.system_id for system in self.systems)
        if len(system_ids) != len(set(system_ids)):
            raise ValueError("Benchmark report system IDs must be unique.")
        expected_observations = self.case_count * self.trials * len(self.systems)
        if len(self.observations) != expected_observations:
            raise ValueError("Benchmark report must retain one observation per attempt.")
        if not all(
            isinstance(observation, BenchmarkAttemptObservation)
            and observation.system_id in system_ids
            for observation in self.observations
        ):
            raise ValueError("Benchmark report observations reference unknown systems.")
        observation_keys = tuple(
            (observation.case_id, observation.system_id, observation.trial_index)
            for observation in self.observations
        )
        if len(observation_keys) != len(set(observation_keys)):
            raise ValueError("Benchmark report observations must be uniquely keyed.")
        if any(observation.trial_index >= self.trials for observation in self.observations):
            raise ValueError("Benchmark report observation trial index is out of range.")
        case_ids = tuple(sorted({observation.case_id for observation in self.observations}))
        if len(case_ids) != self.case_count:
            raise ValueError("Benchmark report observation case coverage is incomplete.")
        expected_keys = {
            (case_id, system_id, trial_index)
            for case_id in case_ids
            for system_id in system_ids
            for trial_index in range(self.trials)
        }
        if set(observation_keys) != expected_keys:
            raise ValueError("Benchmark report observations must cover every configured attempt.")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset": {
                "dataset_id": self.dataset_id,
                "dataset_version": self.dataset_version,
                "digest": self.dataset_digest,
                "case_count": self.case_count,
            },
            "annotations": {
                "annotation_set_id": self.annotation_set_id,
                "annotation_set_version": self.annotation_set_version,
                "digest": self.annotation_digest,
            },
            "configuration": {
                "trials": self.trials,
                "budget": self.budget.to_dict(),
                "metric_context": self.metric_context.to_dict(),
            },
            "systems": [system.to_dict() for system in self.systems],
            "observations": [observation.to_dict() for observation in self.observations],
        }


def _require_identifier(value: object, name: str) -> None:
    if not isinstance(value, str) or len(value) > 128 or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical identifier.")


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(f"{name} must be non-empty text no longer than 256 characters.")


def _require_digest(value: object, name: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest.")


def _require_positive_int(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")


def _require_nonnegative_int(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer.")


def _normalized_float(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a finite normalized number.")
    converted = float(value)
    if not math.isfinite(converted) or not 0.0 <= converted <= 1.0:
        raise ValueError(f"{name} must be a finite normalized number.")
    return converted


__all__ = [
    "BENCHMARK_REPORT_SCHEMA_VERSION",
    "NO_APPLICABLE_SAMPLES",
    "NO_RUNTIME_SAMPLES",
    "BenchmarkAttemptObservation",
    "BenchmarkBudget",
    "BenchmarkExecutionMode",
    "BenchmarkFailure",
    "BenchmarkMetricSummary",
    "BenchmarkReport",
    "BenchmarkRuntimeSummary",
    "BenchmarkStage",
    "BenchmarkSystemDescriptor",
    "BenchmarkSystemReport",
    "BenchmarkTrack",
    "BenchmarkTrackObservation",
    "BenchmarkTrackSummary",
]
