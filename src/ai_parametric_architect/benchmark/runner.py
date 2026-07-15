"""Detached two-track benchmark runner for injected intent and planning agents."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ai_parametric_architect.benchmark.data import (
    BenchmarkAnnotationSet,
    BenchmarkCase,
    BenchmarkDataset,
    ReferenceAnnotation,
)
from ai_parametric_architect.benchmark.models import (
    NO_APPLICABLE_SAMPLES,
    NO_RUNTIME_SAMPLES,
    BenchmarkAttemptObservation,
    BenchmarkBudget,
    BenchmarkFailure,
    BenchmarkMetricSummary,
    BenchmarkReport,
    BenchmarkRuntimeSummary,
    BenchmarkStage,
    BenchmarkSystemDescriptor,
    BenchmarkSystemReport,
    BenchmarkTrack,
    BenchmarkTrackObservation,
    BenchmarkTrackSummary,
)
from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.planning_errors import PlanningError
from ai_parametric_architect.evaluation.metrics.intent import IntentExtractionAccuracy
from ai_parametric_architect.evaluation.metrics.models import MetricResult, summarize_binary
from ai_parametric_architect.evaluation.metrics.plan import PlanValidity
from ai_parametric_architect.evaluation.planning_metrics.evaluator import (
    PlanningMetricsEvaluator,
)
from ai_parametric_architect.evaluation.planning_metrics.models import (
    PlanningMetricContext,
    PlanningMetricsReport,
)
from ai_parametric_architect.evaluation.scenarios.models import Scenario
from ai_parametric_architect.planning.models import FloorPlanProposal

EXACT_REFERENCE_INTENT_REQUIRED = "EXACT_REFERENCE_INTENT_REQUIRED"
PLANNING_SUCCESS = "planning_success"


class IntentAgent(Protocol):
    """Minimal provider-neutral parser boundary."""

    def run(self, value: str) -> DesignIntent: ...


class FloorPlanAgent(Protocol):
    """Minimal detached proposal boundary."""

    def run(self, value: DesignIntent) -> FloorPlanProposal: ...


@runtime_checkable
class MonotonicClock(Protocol):
    """Injected nanosecond clock; keeps runtime evidence deterministic in tests."""

    def monotonic_ns(self) -> int: ...


@dataclass(frozen=True, slots=True)
class BenchmarkSystem:
    """One frozen descriptor plus its non-serializable injected agents."""

    descriptor: BenchmarkSystemDescriptor
    intent_agent: IntentAgent = field(repr=False)
    floor_plan_agent: FloorPlanAgent = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, BenchmarkSystemDescriptor):
            raise TypeError("descriptor must be a BenchmarkSystemDescriptor.")
        if not callable(getattr(self.intent_agent, "run", None)):
            raise TypeError("intent_agent must implement run(str).")
        if not callable(getattr(self.floor_plan_agent, "run", None)):
            raise TypeError("floor_plan_agent must implement run(DesignIntent).")


@dataclass(frozen=True, slots=True)
class _PlanRun:
    plan: FloorPlanProposal | None
    runtime_ns: int
    failure: BenchmarkFailure | None


@dataclass(frozen=True, slots=True)
class _CompletedAttempt:
    observation: BenchmarkAttemptObservation
    end_to_end_plan: FloorPlanProposal | None = field(repr=False)
    oracle_intent_plan: FloorPlanProposal | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class _SpatialSummaries:
    constraint_satisfaction: BenchmarkMetricSummary
    spatial_efficiency: BenchmarkMetricSummary
    circulation: BenchmarkMetricSummary
    stability: BenchmarkMetricSummary


@dataclass(frozen=True, slots=True)
class BenchmarkRunner:
    """Run parsers/planners as detached proposal producers; never patch or commit."""

    metric_context: PlanningMetricContext
    clock: MonotonicClock = field(repr=False)
    budget: BenchmarkBudget = field(default_factory=BenchmarkBudget)
    intent_metric: IntentExtractionAccuracy = field(
        default_factory=IntentExtractionAccuracy,
        repr=False,
    )
    plan_metric: PlanValidity = field(default_factory=PlanValidity, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.metric_context, PlanningMetricContext):
            raise TypeError("metric_context must be a PlanningMetricContext.")
        if not isinstance(self.clock, MonotonicClock):
            raise TypeError("clock must implement monotonic_ns().")
        if not isinstance(self.budget, BenchmarkBudget):
            raise TypeError("budget must be a BenchmarkBudget.")

    def run(
        self,
        dataset: BenchmarkDataset,
        annotations: BenchmarkAnnotationSet,
        systems: Sequence[BenchmarkSystem],
        *,
        trials: int = 1,
    ) -> BenchmarkReport:
        """Evaluate every system/case/trial in end-to-end and oracle-intent tracks."""

        if type(dataset) is not BenchmarkDataset:
            raise TypeError("dataset must be an exact BenchmarkDataset.")
        if type(annotations) is not BenchmarkAnnotationSet:
            raise TypeError("annotations must be an exact BenchmarkAnnotationSet.")
        system_values = tuple(systems)
        if not system_values or not all(
            type(system) is BenchmarkSystem for system in system_values
        ):
            raise TypeError("systems must contain exact BenchmarkSystem values.")

        # Complete cost and evaluator limits are checked before any clock or agent call.
        self.budget.require(
            case_count=len(dataset.cases),
            system_count=len(system_values),
            trials=trials,
        )
        if trials > self.metric_context.max_runs:
            raise ValueError("Benchmark trials exceed the planning metric run budget.")
        system_ids = tuple(system.descriptor.system_id for system in system_values)
        if len(system_ids) != len(set(system_ids)):
            raise ValueError("Benchmark system IDs must be unique.")
        annotations.require_dataset(dataset)
        references = {annotation.case_id: annotation for annotation in annotations.annotations}

        all_completed: list[_CompletedAttempt] = []
        system_reports: list[BenchmarkSystemReport] = []
        for system in system_values:
            completed: list[_CompletedAttempt] = []
            for case in dataset.cases:
                reference = references[case.case_id]
                scenario = _reference_scenario(case, reference)
                for trial_index in range(trials):
                    completed.append(
                        self._run_attempt(
                            system=system,
                            case=case,
                            scenario=scenario,
                            trial_index=trial_index,
                        )
                    )
            completed_values = tuple(completed)
            all_completed.extend(completed_values)
            system_reports.append(self._summarize_system(system, completed_values))

        return BenchmarkReport(
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            dataset_digest=dataset.digest,
            annotation_set_id=annotations.annotation_set_id,
            annotation_set_version=annotations.annotation_set_version,
            annotation_digest=annotations.digest,
            case_count=len(dataset.cases),
            trials=trials,
            budget=self.budget,
            metric_context=self.metric_context,
            systems=tuple(system_reports),
            observations=tuple(value.observation for value in all_completed),
        )

    def _run_attempt(
        self,
        *,
        system: BenchmarkSystem,
        case: BenchmarkCase,
        scenario: Scenario,
        trial_index: int,
    ) -> _CompletedAttempt:
        intent, parse_runtime_ns, intent_failure = self._run_intent(
            system.intent_agent,
            case.input_requirement,
        )
        intent_exact = intent is not None and self.intent_metric.matches(intent, scenario)

        end_to_end_plan: FloorPlanProposal | None = None
        if intent is None:
            end_to_end = BenchmarkTrackObservation(
                track=BenchmarkTrack.END_TO_END,
                planning_succeeded=False,
                plan_valid=False,
                proposal_digest=None,
                parse_runtime_ns=parse_runtime_ns,
                plan_runtime_ns=None,
                total_runtime_ns=parse_runtime_ns,
                failure=intent_failure,
            )
        else:
            end_to_end_run = self._run_plan(
                system.floor_plan_agent,
                intent,
                expected_strategy=system.descriptor.planner_strategy,
            )
            end_to_end_plan = end_to_end_run.plan
            end_to_end = _plan_observation(
                track=BenchmarkTrack.END_TO_END,
                scenario=scenario,
                plan_run=end_to_end_run,
                parse_runtime_ns=parse_runtime_ns,
                plan_metric=self.plan_metric,
            )

        oracle_run = self._run_plan(
            system.floor_plan_agent,
            scenario.expected_intent,
            expected_strategy=system.descriptor.planner_strategy,
        )
        oracle_intent = _plan_observation(
            track=BenchmarkTrack.ORACLE_INTENT,
            scenario=scenario,
            plan_run=oracle_run,
            parse_runtime_ns=None,
            plan_metric=self.plan_metric,
        )
        observation = BenchmarkAttemptObservation(
            case_id=case.case_id,
            system_id=system.descriptor.system_id,
            trial_index=trial_index,
            intent_exact=intent_exact,
            end_to_end=end_to_end,
            oracle_intent=oracle_intent,
        )
        return _CompletedAttempt(
            observation=observation,
            end_to_end_plan=end_to_end_plan,
            oracle_intent_plan=oracle_run.plan,
        )

    def _run_intent(
        self,
        agent: IntentAgent,
        requirement: str,
    ) -> tuple[DesignIntent | None, int, BenchmarkFailure | None]:
        started = _read_clock(self.clock)
        try:
            intent = agent.run(requirement)
        except PlanningError as error:
            runtime_ns = _elapsed(started, _read_clock(self.clock))
            return None, runtime_ns, _known_failure(BenchmarkStage.INTENT, error)
        runtime_ns = _elapsed(started, _read_clock(self.clock))
        if type(intent) is not DesignIntent:
            raise TypeError("Benchmark intent agents must return an exact DesignIntent.")
        return intent, runtime_ns, None

    def _run_plan(
        self,
        agent: FloorPlanAgent,
        intent: DesignIntent,
        *,
        expected_strategy: str,
    ) -> _PlanRun:
        started = _read_clock(self.clock)
        try:
            plan = agent.run(intent)
        except PlanningError as error:
            runtime_ns = _elapsed(started, _read_clock(self.clock))
            return _PlanRun(
                plan=None,
                runtime_ns=runtime_ns,
                failure=_known_failure(BenchmarkStage.PLAN, error),
            )
        runtime_ns = _elapsed(started, _read_clock(self.clock))
        if type(plan) is not FloorPlanProposal:
            raise TypeError("Benchmark floor-plan agents must return an exact FloorPlanProposal.")
        if plan.intent != intent:
            raise TypeError("Benchmark floor-plan outputs must retain their input DesignIntent.")
        if plan.strategy != expected_strategy:
            raise TypeError("Benchmark floor-plan strategy does not match its system descriptor.")
        return _PlanRun(plan=plan, runtime_ns=runtime_ns, failure=None)

    def _summarize_system(
        self,
        system: BenchmarkSystem,
        completed: tuple[_CompletedAttempt, ...],
    ) -> BenchmarkSystemReport:
        attempt_count = len(completed)
        accuracy = self.intent_metric.summarize(
            value.observation.intent_exact for value in completed
        )
        return BenchmarkSystemReport(
            descriptor=system.descriptor,
            attempt_count=attempt_count,
            intent_extraction_accuracy=_binary_summary(accuracy, attempt_count),
            end_to_end=self._summarize_track(
                completed,
                BenchmarkTrack.END_TO_END,
            ),
            oracle_intent=self._summarize_track(
                completed,
                BenchmarkTrack.ORACLE_INTENT,
            ),
        )

    def _summarize_track(
        self,
        completed: tuple[_CompletedAttempt, ...],
        track: BenchmarkTrack,
    ) -> BenchmarkTrackSummary:
        observations = tuple(_track_observation(value, track) for value in completed)
        attempt_count = len(observations)
        planning_success = summarize_binary(
            PLANNING_SUCCESS,
            (observation.planning_succeeded for observation in observations),
        )
        plan_validity = self.plan_metric.summarize(
            observation.plan_valid for observation in observations
        )
        spatial = self._summarize_spatial(completed, track)
        return BenchmarkTrackSummary(
            track=track,
            planning_success=_binary_summary(planning_success, attempt_count),
            plan_validity=_binary_summary(plan_validity, attempt_count),
            constraint_satisfaction=spatial.constraint_satisfaction,
            spatial_efficiency=spatial.spatial_efficiency,
            circulation=spatial.circulation,
            stability=spatial.stability,
            parse_runtime=_runtime_summary(
                "parse_runtime_ns",
                tuple(observation.parse_runtime_ns for observation in observations),
                attempt_count,
            ),
            plan_runtime=_runtime_summary(
                "plan_runtime_ns",
                tuple(observation.plan_runtime_ns for observation in observations),
                attempt_count,
            ),
            total_runtime=_runtime_summary(
                "total_runtime_ns",
                tuple(observation.total_runtime_ns for observation in observations),
                attempt_count,
            ),
        )

    def _summarize_spatial(
        self,
        completed: tuple[_CompletedAttempt, ...],
        track: BenchmarkTrack,
    ) -> _SpatialSummaries:
        attempt_count = len(completed)
        grouped: dict[str, list[FloorPlanProposal]] = {}
        exact_reference_count = sum(value.observation.intent_exact for value in completed)
        for value in completed:
            if track is BenchmarkTrack.END_TO_END:
                if not value.observation.intent_exact:
                    continue
                plan = value.end_to_end_plan
            else:
                plan = value.oracle_intent_plan
            if plan is None:
                continue
            grouped.setdefault(value.observation.case_id, []).append(plan)

        constraint_values: list[float] = []
        efficiency_values: list[float] = []
        circulation_values: list[float] = []
        constraint_reasons: set[str] = set()
        efficiency_reasons: set[str] = set()
        circulation_reasons: set[str] = set()
        stability_reasons: set[str] = set()
        stability_weighted_total = 0.0
        stability_sample_count = 0
        stability_covered_attempts = 0
        evaluator = PlanningMetricsEvaluator(self.metric_context)
        for plans in grouped.values():
            report = evaluator.evaluate(tuple(plans))
            for observation in report.observations:
                if observation.constraint_satisfaction is not None:
                    constraint_values.append(observation.constraint_satisfaction)
                if observation.spatial_efficiency is not None:
                    efficiency_values.append(observation.spatial_efficiency)
                if observation.circulation is not None:
                    circulation_values.append(observation.circulation)
            _record_reason(report, "constraint_satisfaction_score", constraint_reasons)
            _record_reason(report, "spatial_efficiency_score", efficiency_reasons)
            _record_reason(report, "circulation_score", circulation_reasons)
            stability = report.plan_stability_score
            if stability.value is None:
                assert stability.reason is not None
                stability_reasons.add(stability.reason)
            else:
                stability_weighted_total += stability.value * stability.sample_count
                stability_sample_count += stability.sample_count
                stability_covered_attempts += len(plans)

        empty_reason = (
            EXACT_REFERENCE_INTENT_REQUIRED
            if track is BenchmarkTrack.END_TO_END and exact_reference_count == 0
            else NO_APPLICABLE_SAMPLES
        )
        return _SpatialSummaries(
            constraint_satisfaction=_score_summary(
                "constraint_satisfaction_score",
                tuple(constraint_values),
                attempt_count=attempt_count,
                reasons=constraint_reasons,
                empty_reason=empty_reason,
            ),
            spatial_efficiency=_score_summary(
                "spatial_efficiency_score",
                tuple(efficiency_values),
                attempt_count=attempt_count,
                reasons=efficiency_reasons,
                empty_reason=empty_reason,
            ),
            circulation=_score_summary(
                "circulation_score",
                tuple(circulation_values),
                attempt_count=attempt_count,
                reasons=circulation_reasons,
                empty_reason=empty_reason,
            ),
            stability=_weighted_score_summary(
                "plan_stability_score",
                weighted_total=stability_weighted_total,
                sample_count=stability_sample_count,
                covered_attempt_count=stability_covered_attempts,
                attempt_count=attempt_count,
                reasons=stability_reasons,
                empty_reason=empty_reason,
            ),
        )


def _reference_scenario(case: BenchmarkCase, reference: ReferenceAnnotation) -> Scenario:
    return Scenario(
        input_requirement=case.input_requirement,
        expected_intent=reference.expected_intent,
        expected_constraints=reference.expected_constraints,
    )


def _plan_observation(
    *,
    track: BenchmarkTrack,
    scenario: Scenario,
    plan_run: _PlanRun,
    parse_runtime_ns: int | None,
    plan_metric: PlanValidity,
) -> BenchmarkTrackObservation:
    plan = plan_run.plan
    return BenchmarkTrackObservation(
        track=track,
        planning_succeeded=plan is not None,
        plan_valid=plan is not None and plan_metric.is_valid(plan, scenario),
        proposal_digest=None if plan is None else _proposal_digest(plan),
        parse_runtime_ns=parse_runtime_ns,
        plan_runtime_ns=plan_run.runtime_ns,
        total_runtime_ns=(parse_runtime_ns or 0) + plan_run.runtime_ns,
        failure=plan_run.failure,
    )


def _track_observation(
    completed: _CompletedAttempt,
    track: BenchmarkTrack,
) -> BenchmarkTrackObservation:
    if track is BenchmarkTrack.END_TO_END:
        return completed.observation.end_to_end
    return completed.observation.oracle_intent


def _known_failure(stage: BenchmarkStage, error: PlanningError) -> BenchmarkFailure:
    return BenchmarkFailure(stage=stage, code=error.code, path=error.path)


def _proposal_digest(plan: FloorPlanProposal) -> str:
    payload = json.dumps(
        plan.to_dict(),
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_clock(clock: MonotonicClock) -> int:
    value = clock.monotonic_ns()
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("Monotonic clock values must be non-negative integer nanoseconds.")
    return value


def _elapsed(started: int, finished: int) -> int:
    if finished < started:
        raise ValueError("Monotonic clock moved backwards.")
    return finished - started


def _binary_summary(result: MetricResult, attempt_count: int) -> BenchmarkMetricSummary:
    if result.total != attempt_count:
        raise ValueError("Binary benchmark metrics must include every attempt.")
    return BenchmarkMetricSummary(
        name=result.name,
        value=result.value,
        attempt_count=attempt_count,
        covered_attempt_count=attempt_count,
        sample_count=attempt_count,
        successes=result.successes,
    )


def _score_summary(
    name: str,
    values: tuple[float, ...],
    *,
    attempt_count: int,
    reasons: set[str],
    empty_reason: str,
) -> BenchmarkMetricSummary:
    if not values:
        return BenchmarkMetricSummary(
            name=name,
            value=None,
            attempt_count=attempt_count,
            covered_attempt_count=0,
            sample_count=0,
            reason=_summary_reason(reasons, empty_reason),
        )
    return BenchmarkMetricSummary(
        name=name,
        value=math.fsum(values) / len(values),
        attempt_count=attempt_count,
        covered_attempt_count=len(values),
        sample_count=len(values),
    )


def _weighted_score_summary(
    name: str,
    *,
    weighted_total: float,
    sample_count: int,
    covered_attempt_count: int,
    attempt_count: int,
    reasons: set[str],
    empty_reason: str,
) -> BenchmarkMetricSummary:
    if sample_count == 0:
        return BenchmarkMetricSummary(
            name=name,
            value=None,
            attempt_count=attempt_count,
            covered_attempt_count=0,
            sample_count=0,
            reason=_summary_reason(reasons, empty_reason),
        )
    return BenchmarkMetricSummary(
        name=name,
        value=weighted_total / sample_count,
        attempt_count=attempt_count,
        covered_attempt_count=covered_attempt_count,
        sample_count=sample_count,
    )


def _runtime_summary(
    name: str,
    observations: tuple[int | None, ...],
    attempt_count: int,
) -> BenchmarkRuntimeSummary:
    values = tuple(sorted(value for value in observations if value is not None))
    if not values:
        return BenchmarkRuntimeSummary(
            name=name,
            attempt_count=attempt_count,
            covered_attempt_count=0,
            sample_count=0,
            minimum_ns=None,
            median_ns=None,
            p95_ns=None,
            maximum_ns=None,
            total_ns=None,
            reason=NO_RUNTIME_SAMPLES,
        )
    return BenchmarkRuntimeSummary(
        name=name,
        attempt_count=attempt_count,
        covered_attempt_count=len(values),
        sample_count=len(values),
        minimum_ns=values[0],
        median_ns=values[_nearest_rank_index(len(values), 50)],
        p95_ns=values[_nearest_rank_index(len(values), 95)],
        maximum_ns=values[-1],
        total_ns=sum(values),
    )


def _nearest_rank_index(sample_count: int, percentile: int) -> int:
    return max(0, ((sample_count * percentile + 99) // 100) - 1)


def _record_reason(
    report: PlanningMetricsReport,
    metric_name: str,
    reasons: set[str],
) -> None:
    metric = getattr(report, metric_name)
    if metric.value is None:
        assert metric.reason is not None
        reasons.add(metric.reason)


def _summary_reason(reasons: set[str], fallback: str) -> str:
    if len(reasons) == 1:
        return next(iter(reasons))
    return fallback


__all__ = [
    "EXACT_REFERENCE_INTENT_REQUIRED",
    "BenchmarkRunner",
    "BenchmarkSystem",
    "FloorPlanAgent",
    "IntentAgent",
    "MonotonicClock",
]
