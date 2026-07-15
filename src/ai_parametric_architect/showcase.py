"""Versioned detached proposal-preview artifacts for deterministic offline replay."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from ai_parametric_architect.domain.design_intent import DesignIntent
from ai_parametric_architect.domain.planning_errors import PlanningError
from ai_parametric_architect.evaluation.planning_metrics.models import (
    NormalizedMetricResult,
    PlanningMetricContext,
    PlanningMetricsReport,
)
from ai_parametric_architect.planning.models import (
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    FloorPlanProposal,
)

SHOWCASE_SCHEMA_VERSION: Final = "1.0.0"
SHOWCASE_ARTIFACT_KIND: Final = "detached_floor_plan_showcase"
SHOWCASE_EXECUTION_MODE: Final = "deterministic_offline_replay"
MAX_SHOWCASE_SCENARIOS: Final = 16
MAX_SHOWCASE_REQUIREMENT_BYTES: Final = 16 * 1024

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,127}$")
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ShowcaseStatus(StrEnum):
    SUCCESS = "success"
    REJECTED = "rejected"


class ShowcaseStage(StrEnum):
    INTENT = "intent"
    PLAN = "plan"


class ShowcaseIntentAgent(Protocol):
    def run(self, value: str) -> DesignIntent: ...


class ShowcaseFloorPlanAgent(Protocol):
    def run(self, value: DesignIntent) -> FloorPlanProposal: ...


class ShowcaseEvidenceFactory(Protocol):
    def __call__(
        self,
        case: ShowcaseCase,
        intent: DesignIntent,
        proposal: FloorPlanProposal,
    ) -> ShowcaseScenarioEvidence: ...


@dataclass(frozen=True, slots=True)
class ShowcaseCase:
    scenario_id: str
    title: str
    input_requirement: str

    def __post_init__(self) -> None:
        _require_identifier(self.scenario_id, "scenario_id")
        _require_text(self.title, "title", maximum=128)
        _require_text(self.input_requirement, "input_requirement", maximum=32_768)
        try:
            size = len(self.input_requirement.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise ValueError("input_requirement must be valid UTF-8 text.") from error
        if size > MAX_SHOWCASE_REQUIREMENT_BYTES:
            raise ValueError("input_requirement exceeds the showcase byte budget.")


@dataclass(frozen=True, slots=True)
class ShowcaseFailure:
    """Stable known failure without exception message, details, or provider payload."""

    stage: ShowcaseStage
    code: str
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.stage, ShowcaseStage):
            raise TypeError("stage must be a ShowcaseStage.")
        if not isinstance(self.code, str) or _ERROR_CODE.fullmatch(self.code) is None:
            raise ValueError("code must be a canonical stable error code.")
        if not isinstance(self.path, str) or (self.path and not self.path.startswith("/")):
            raise ValueError("path must be empty or a JSON pointer.")

    def to_dict(self) -> dict[str, str]:
        return {"stage": self.stage.value, "code": self.code, "path": self.path}


@dataclass(frozen=True, slots=True)
class ShowcaseExecution:
    intent_agent_name: str
    intent_agent_version: str
    floor_plan_agent_name: str
    floor_plan_agent_version: str
    planner_strategy: str
    rules_version: str
    random_seed: int
    mode: str = SHOWCASE_EXECUTION_MODE

    def __post_init__(self) -> None:
        if self.mode != SHOWCASE_EXECUTION_MODE:
            raise ValueError("Showcase execution must be a deterministic offline replay.")
        for name, value in (
            ("intent_agent_name", self.intent_agent_name),
            ("intent_agent_version", self.intent_agent_version),
            ("floor_plan_agent_name", self.floor_plan_agent_name),
            ("floor_plan_agent_version", self.floor_plan_agent_version),
            ("planner_strategy", self.planner_strategy),
            ("rules_version", self.rules_version),
        ):
            _require_text(value, name, maximum=256)
        if (
            not isinstance(self.random_seed, int)
            or isinstance(self.random_seed, bool)
            or self.random_seed < 0
        ):
            raise ValueError("random_seed must be a non-negative integer.")

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "intent_parser": {
                "name": self.intent_agent_name,
                "version": self.intent_agent_version,
            },
            "planner": {
                "name": self.floor_plan_agent_name,
                "version": self.floor_plan_agent_version,
                "strategy": self.planner_strategy,
                "rules_version": self.rules_version,
                "random_seed": self.random_seed,
            },
        }


@dataclass(frozen=True, slots=True)
class ShowcaseSystemEvidence:
    """One real PlanningMetricsEvaluator result for one detached proposal."""

    system_id: str
    strategy: str
    proposal_digest: str
    report: PlanningMetricsReport

    def __post_init__(self) -> None:
        _require_identifier(self.system_id, "system_id")
        _require_text(self.strategy, "strategy", maximum=256)
        if (
            not isinstance(self.proposal_digest, str)
            or _SHA256.fullmatch(self.proposal_digest) is None
        ):
            raise ValueError("proposal_digest must be a lowercase SHA-256 digest.")
        if not isinstance(self.report, PlanningMetricsReport):
            raise TypeError("report must be a PlanningMetricsReport.")
        if len(self.report.observations) != 1:
            raise ValueError("Showcase system evidence must score exactly one proposal.")
        if self.report.observations[0].strategy != self.strategy:
            raise ValueError("Showcase evidence strategy must match its scored proposal.")

    def to_dict(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "strategy": self.strategy,
            "proposal_digest": self.proposal_digest,
            "metrics": {
                "constraint_satisfaction": _metric_dict(self.report.constraint_satisfaction_score),
                "spatial_efficiency": _metric_dict(self.report.spatial_efficiency_score),
                "circulation": _metric_dict(self.report.circulation_score),
                "stability": _metric_dict(self.report.plan_stability_score),
            },
        }


@dataclass(frozen=True, slots=True)
class ShowcaseScenarioEvidence:
    metric_context: PlanningMetricContext
    systems: tuple[ShowcaseSystemEvidence, ...]
    schema_version: str = SHOWCASE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SHOWCASE_SCHEMA_VERSION:
            raise ValueError("Unsupported showcase evidence schema version.")
        if not isinstance(self.metric_context, PlanningMetricContext):
            raise TypeError("metric_context must be a PlanningMetricContext.")
        if not self.systems or not all(
            type(value) is ShowcaseSystemEvidence for value in self.systems
        ):
            raise ValueError("Showcase evidence requires exact system evidence values.")
        system_ids = tuple(value.system_id for value in self.systems)
        if len(system_ids) != len(set(system_ids)):
            raise ValueError("Showcase evidence system IDs must be unique.")
        if any(value.report.metric_context != self.metric_context for value in self.systems):
            raise ValueError("Showcase evidence must use one shared metric context.")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_context": self.metric_context.to_dict(),
            "systems": [value.to_dict() for value in self.systems],
        }


@dataclass(frozen=True, slots=True)
class ShowcaseScenario:
    scenario_id: str
    title: str
    input_requirement: str
    status: ShowcaseStatus
    intent: DesignIntent | None
    proposal: FloorPlanProposal | None
    proposal_digest: str | None
    failure: ShowcaseFailure | None
    evidence: ShowcaseScenarioEvidence | None

    def __post_init__(self) -> None:
        ShowcaseCase(self.scenario_id, self.title, self.input_requirement)
        if not isinstance(self.status, ShowcaseStatus):
            raise TypeError("status must be a ShowcaseStatus.")
        if self.status is ShowcaseStatus.SUCCESS:
            if type(self.intent) is not DesignIntent:
                raise TypeError("Successful showcase scenarios require an exact DesignIntent.")
            if type(self.proposal) is not FloorPlanProposal:
                raise TypeError("Successful showcase scenarios require an exact proposal.")
            if self.proposal.schema_version != SOLVED_FLOOR_PLAN_SCHEMA_VERSION:
                raise ValueError("Showcase previews require a solved v2 proposal.")
            if self.proposal.intent != self.intent:
                raise ValueError("Showcase proposal intent must equal the extracted intent.")
            if self.proposal_digest != canonical_proposal_digest(self.proposal):
                raise ValueError("Showcase proposal digest does not match the proposal.")
            if self.failure is not None:
                raise ValueError("Successful showcase scenarios cannot contain a failure.")
            if not isinstance(self.evidence, ShowcaseScenarioEvidence):
                raise TypeError("Successful showcase scenarios require metric evidence.")
            if not any(
                value.strategy == self.proposal.strategy
                and value.proposal_digest == self.proposal_digest
                for value in self.evidence.systems
            ):
                raise ValueError("Showcase evidence must include the primary proposal.")
            return
        if not isinstance(self.failure, ShowcaseFailure):
            raise TypeError("Rejected showcase scenarios require a stable failure.")
        if self.proposal is not None or self.proposal_digest is not None:
            raise ValueError("Rejected showcase scenarios cannot retain proposal output.")
        if self.failure.stage is ShowcaseStage.INTENT and self.intent is not None:
            raise ValueError("Intent-stage failures cannot retain a DesignIntent.")
        if self.failure.stage is ShowcaseStage.PLAN and type(self.intent) is not DesignIntent:
            raise TypeError("Plan-stage failures must retain the parsed DesignIntent.")
        if self.evidence is not None:
            raise ValueError("Rejected showcase scenarios cannot contain metric evidence.")

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "input_requirement": self.input_requirement,
            "status": self.status.value,
            "intent": None if self.intent is None else self.intent.to_dict(),
            "proposal": None if self.proposal is None else self.proposal.to_dict(),
            "proposal_digest": self.proposal_digest,
            "failure": None if self.failure is None else self.failure.to_dict(),
            "evidence": None if self.evidence is None else self.evidence.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PlanningShowcaseArtifact:
    execution: ShowcaseExecution
    scenarios: tuple[ShowcaseScenario, ...]
    schema_version: str = SHOWCASE_SCHEMA_VERSION
    artifact_kind: str = SHOWCASE_ARTIFACT_KIND

    def __post_init__(self) -> None:
        if self.schema_version != SHOWCASE_SCHEMA_VERSION:
            raise ValueError("Unsupported showcase schema version.")
        if self.artifact_kind != SHOWCASE_ARTIFACT_KIND:
            raise ValueError("Unsupported showcase artifact kind.")
        if not isinstance(self.execution, ShowcaseExecution):
            raise TypeError("execution must be a ShowcaseExecution.")
        if (
            not isinstance(self.scenarios, tuple)
            or not 1 <= len(self.scenarios) <= MAX_SHOWCASE_SCENARIOS
            or not all(type(value) is ShowcaseScenario for value in self.scenarios)
        ):
            raise ValueError("scenarios must be a bounded tuple of exact scenario values.")
        scenario_ids = tuple(value.scenario_id for value in self.scenarios)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Showcase scenario IDs must be unique.")
        for scenario in self.scenarios:
            if (
                scenario.proposal is not None
                and scenario.proposal.strategy != self.execution.planner_strategy
            ):
                raise ValueError("Showcase proposal strategy must match execution metadata.")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_kind": self.artifact_kind,
            "execution": self.execution.to_dict(),
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
        }


def build_planning_showcase(
    *,
    cases: Sequence[ShowcaseCase],
    execution: ShowcaseExecution,
    intent_agent: ShowcaseIntentAgent,
    floor_plan_agent: ShowcaseFloorPlanAgent,
    evidence_factory: ShowcaseEvidenceFactory,
) -> PlanningShowcaseArtifact:
    """Run injected proposal-only agents; known errors become redacted showcase outcomes."""

    case_values = tuple(cases)
    if not case_values or not all(type(value) is ShowcaseCase for value in case_values):
        raise TypeError("cases must contain exact ShowcaseCase values.")
    scenarios: list[ShowcaseScenario] = []
    for case in case_values:
        try:
            intent = intent_agent.run(case.input_requirement)
        except PlanningError as error:
            scenarios.append(_rejected(case, ShowcaseStage.INTENT, error))
            continue
        if type(intent) is not DesignIntent:
            raise TypeError("Showcase intent agent must return an exact DesignIntent.")
        try:
            proposal = floor_plan_agent.run(intent)
        except PlanningError as error:
            scenarios.append(_rejected(case, ShowcaseStage.PLAN, error, intent=intent))
            continue
        if type(proposal) is not FloorPlanProposal:
            raise TypeError("Showcase planner must return an exact FloorPlanProposal.")
        scenarios.append(
            ShowcaseScenario(
                scenario_id=case.scenario_id,
                title=case.title,
                input_requirement=case.input_requirement,
                status=ShowcaseStatus.SUCCESS,
                intent=intent,
                proposal=proposal,
                proposal_digest=canonical_proposal_digest(proposal),
                failure=None,
                evidence=evidence_factory(case, intent, proposal),
            )
        )
    return PlanningShowcaseArtifact(execution=execution, scenarios=tuple(scenarios))


def canonical_proposal_digest(proposal: FloorPlanProposal) -> str:
    if type(proposal) is not FloorPlanProposal:
        raise TypeError("proposal must be an exact FloorPlanProposal.")
    encoded = json.dumps(
        proposal.to_dict(),
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rejected(
    case: ShowcaseCase,
    stage: ShowcaseStage,
    error: PlanningError,
    *,
    intent: DesignIntent | None = None,
) -> ShowcaseScenario:
    return ShowcaseScenario(
        scenario_id=case.scenario_id,
        title=case.title,
        input_requirement=case.input_requirement,
        status=ShowcaseStatus.REJECTED,
        intent=intent,
        proposal=None,
        proposal_digest=None,
        failure=ShowcaseFailure(stage=stage, code=error.code, path=error.path),
        evidence=None,
    )


def _metric_dict(metric: NormalizedMetricResult) -> dict[str, object]:
    return metric.to_dict()


def _require_identifier(value: object, name: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical lowercase identifier.")


def _require_text(value: object, name: str, *, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > maximum
    ):
        raise ValueError(f"{name} must be canonical non-empty text.")


__all__ = [
    "MAX_SHOWCASE_REQUIREMENT_BYTES",
    "MAX_SHOWCASE_SCENARIOS",
    "SHOWCASE_ARTIFACT_KIND",
    "SHOWCASE_EXECUTION_MODE",
    "SHOWCASE_SCHEMA_VERSION",
    "PlanningShowcaseArtifact",
    "ShowcaseCase",
    "ShowcaseEvidenceFactory",
    "ShowcaseExecution",
    "ShowcaseFailure",
    "ShowcaseFloorPlanAgent",
    "ShowcaseIntentAgent",
    "ShowcaseScenario",
    "ShowcaseScenarioEvidence",
    "ShowcaseStage",
    "ShowcaseStatus",
    "ShowcaseSystemEvidence",
    "build_planning_showcase",
    "canonical_proposal_digest",
]
