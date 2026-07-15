"""Strict, immutable dataset and external-reference annotation contracts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from ai_parametric_architect.domain.design_intent import DesignIntent, SpatialConstraint
from ai_parametric_architect.domain.planning_errors import InvalidDesignIntentError

BENCHMARK_DATA_SCHEMA_VERSION: Final = "1.0.0"
MAX_BENCHMARK_CASES: Final = 64
MAX_REQUIREMENT_BYTES: Final = 16 * 1024
MAX_BENCHMARK_FILE_BYTES: Final = 1024 * 1024
MAX_TAGS_PER_CASE: Final = 16
_MAX_NUMBER_CHARACTERS: Final = 128

_IDENTIFIER_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_TAG_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_VERSION_PATTERN: Final = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

_DATASET_FIELDS: Final = {
    "schema_version",
    "dataset_id",
    "dataset_version",
    "cases",
}
_CASE_FIELDS: Final = {"case_id", "tags", "input_requirement"}
_ANNOTATION_SET_FIELDS: Final = {
    "schema_version",
    "annotation_set_id",
    "annotation_set_version",
    "dataset_id",
    "dataset_version",
    "annotations",
}
_ANNOTATION_FIELDS: Final = {
    "case_id",
    "expected_intent",
    "expected_constraints",
}
_INTENT_FIELDS: Final = {
    "building_type",
    "area",
    "rooms",
    "orientation",
    "spatial_constraints",
}
_CONSTRAINT_FIELDS: Final = {
    "source_room_type",
    "relation",
    "target_room_type",
    "required",
}


class BenchmarkDataError(ValueError):
    """Stable failure raised before malformed benchmark data can be evaluated."""

    code = "BENCHMARK_DATA_INVALID"

    def __init__(self, message: str, *, path: str = "", reason: str) -> None:
        super().__init__(message)
        self.path = path
        self.reason = reason

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "path": self.path,
            "message": str(self),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One untrusted requirement; reference answers live in a separate artifact."""

    case_id: str
    tags: tuple[str, ...]
    input_requirement: str

    def __post_init__(self) -> None:
        _require_identifier(self.case_id, path="/case_id", reason="CASE_ID_INVALID")
        if not isinstance(self.tags, tuple):
            raise _error(
                "Benchmark case tags must be an immutable tuple.",
                path="/tags",
                reason="TAGS_TYPE_INVALID",
            )
        if not 1 <= len(self.tags) <= MAX_TAGS_PER_CASE:
            raise _error(
                "Benchmark case tag count is outside the supported budget.",
                path="/tags",
                reason="TAG_COUNT_INVALID",
            )
        if any(
            not isinstance(tag, str) or _TAG_PATTERN.fullmatch(tag) is None for tag in self.tags
        ):
            raise _error(
                "Benchmark tags must be canonical lowercase tokens.",
                path="/tags",
                reason="TAG_INVALID",
            )
        if self.tags != tuple(sorted(set(self.tags))):
            raise _error(
                "Benchmark tags must be sorted and unique.",
                path="/tags",
                reason="TAGS_NOT_SORTED_UNIQUE",
            )
        if (
            not isinstance(self.input_requirement, str)
            or not self.input_requirement
            or self.input_requirement != self.input_requirement.strip()
        ):
            raise _error(
                "Benchmark input_requirement must be non-empty canonical text.",
                path="/input_requirement",
                reason="REQUIREMENT_INVALID",
            )
        try:
            requirement_size = len(self.input_requirement.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise _error(
                "Benchmark input_requirement must be valid UTF-8 text.",
                path="/input_requirement",
                reason="REQUIREMENT_ENCODING_INVALID",
            ) from error
        if requirement_size > MAX_REQUIREMENT_BYTES:
            raise _error(
                "Benchmark input_requirement exceeds the byte budget.",
                path="/input_requirement",
                reason="REQUIREMENT_TOO_LARGE",
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, path: str = "") -> BenchmarkCase:
        _require_fields(value, _CASE_FIELDS, path=path or "/")
        case_id = value.get("case_id")
        tags = value.get("tags")
        requirement = value.get("input_requirement")
        if not isinstance(case_id, str):
            raise _error(
                "Benchmark case_id must be a string.",
                path=f"{path}/case_id",
                reason="CASE_ID_INVALID",
            )
        if type(tags) is not list or not all(isinstance(tag, str) for tag in tags):
            raise _error(
                "Benchmark tags must be an array of strings.",
                path=f"{path}/tags",
                reason="TAGS_TYPE_INVALID",
            )
        if not isinstance(requirement, str):
            raise _error(
                "Benchmark input_requirement must be a string.",
                path=f"{path}/input_requirement",
                reason="REQUIREMENT_INVALID",
            )
        try:
            return cls(case_id=case_id, tags=tuple(tags), input_requirement=requirement)
        except BenchmarkDataError as error:
            raise _prefix_error(error, path) from error

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "tags": list(self.tags),
            "input_requirement": self.input_requirement,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkDataset:
    """Versioned requirements only; contains no expected answers or world state."""

    dataset_id: str
    dataset_version: str
    cases: tuple[BenchmarkCase, ...]
    schema_version: str = BENCHMARK_DATA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_identifier(self.dataset_id, path="/dataset_id", reason="DATASET_ID_INVALID")
        _require_version(self.dataset_version, path="/dataset_version")
        if (
            not isinstance(self.cases, tuple)
            or not 1 <= len(self.cases) <= MAX_BENCHMARK_CASES
            or not all(type(case) is BenchmarkCase for case in self.cases)
        ):
            raise _error(
                "Benchmark cases must be a bounded immutable tuple of exact BenchmarkCase values.",
                path="/cases",
                reason="CASES_INVALID",
            )
        if self.case_ids != tuple(sorted(set(self.case_ids))):
            raise _error(
                "Benchmark case IDs must be sorted and unique.",
                path="/cases",
                reason="CASE_IDS_NOT_SORTED_UNIQUE",
            )

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(case.case_id for case in self.cases)

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BenchmarkDataset:
        _require_fields(value, _DATASET_FIELDS, path="/")
        schema_version = value.get("schema_version")
        dataset_id = value.get("dataset_id")
        dataset_version = value.get("dataset_version")
        case_values = value.get("cases")
        if not isinstance(schema_version, str):
            raise _error(
                "Benchmark schema_version must be a string.",
                path="/schema_version",
                reason="SCHEMA_VERSION_UNSUPPORTED",
            )
        if not isinstance(dataset_id, str):
            raise _error(
                "Benchmark dataset_id must be a string.",
                path="/dataset_id",
                reason="DATASET_ID_INVALID",
            )
        if not isinstance(dataset_version, str):
            raise _error(
                "Benchmark dataset_version must be a string.",
                path="/dataset_version",
                reason="VERSION_INVALID",
            )
        if type(case_values) is not list:
            raise _error(
                "Benchmark cases must be an array.",
                path="/cases",
                reason="CASES_INVALID",
            )
        if not 1 <= len(case_values) <= MAX_BENCHMARK_CASES:
            raise _error(
                "Benchmark case count is outside the supported budget.",
                path="/cases",
                reason="CASE_COUNT_INVALID",
            )
        cases: list[BenchmarkCase] = []
        for index, case_value in enumerate(case_values):
            if type(case_value) is not dict:
                raise _error(
                    "Each benchmark case must be an object.",
                    path=f"/cases/{index}",
                    reason="CASE_INVALID",
                )
            cases.append(BenchmarkCase.from_dict(case_value, path=f"/cases/{index}"))
        return cls(
            schema_version=schema_version,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            cases=tuple(cases),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True, slots=True)
class ReferenceAnnotation:
    """External reference answer; never authoritative World Model or revision state."""

    case_id: str
    expected_intent: DesignIntent
    expected_constraints: tuple[SpatialConstraint, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.case_id, path="/case_id", reason="CASE_ID_INVALID")
        if type(self.expected_intent) is not DesignIntent:
            raise _error(
                "Reference expected_intent must be an exact DesignIntent.",
                path="/expected_intent",
                reason="EXPECTED_INTENT_INVALID",
            )
        if (
            not isinstance(self.expected_constraints, tuple)
            or not all(type(value) is SpatialConstraint for value in self.expected_constraints)
            or self.expected_constraints != self.expected_intent.spatial_constraints
        ):
            raise _error(
                "Reference constraints must exactly match the expected DesignIntent.",
                path="/expected_constraints",
                reason="EXPECTED_CONSTRAINTS_MISMATCH",
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, path: str = "") -> ReferenceAnnotation:
        _require_fields(value, _ANNOTATION_FIELDS, path=path or "/")
        case_id = value.get("case_id")
        intent_value = value.get("expected_intent")
        constraints_value = value.get("expected_constraints")
        if not isinstance(case_id, str):
            raise _error(
                "Reference case_id must be a string.",
                path=f"{path}/case_id",
                reason="CASE_ID_INVALID",
            )
        if type(intent_value) is not dict:
            raise _error(
                "Reference expected_intent must be an object.",
                path=f"{path}/expected_intent",
                reason="EXPECTED_INTENT_INVALID",
            )
        _require_fields(intent_value, _INTENT_FIELDS, path=f"{path}/expected_intent")
        if type(constraints_value) is not list:
            raise _error(
                "Reference expected_constraints must be an array.",
                path=f"{path}/expected_constraints",
                reason="EXPECTED_CONSTRAINTS_INVALID",
            )
        try:
            intent = DesignIntent.from_dict(intent_value)
        except InvalidDesignIntentError as error:
            raise _error(
                "Reference expected_intent violates the DesignIntent contract.",
                path=f"{path}/expected_intent{error.path}",
                reason="EXPECTED_INTENT_INVALID",
            ) from error
        constraints: list[SpatialConstraint] = []
        for index, constraint_value in enumerate(constraints_value):
            constraint_path = f"{path}/expected_constraints/{index}"
            if type(constraint_value) is not dict:
                raise _error(
                    "Each reference constraint must be an object.",
                    path=constraint_path,
                    reason="EXPECTED_CONSTRAINTS_INVALID",
                )
            _require_fields(constraint_value, _CONSTRAINT_FIELDS, path=constraint_path)
            try:
                constraints.append(SpatialConstraint.from_dict(constraint_value))
            except InvalidDesignIntentError as error:
                raise _error(
                    "Reference constraint violates the DesignIntent contract.",
                    path=f"{constraint_path}{error.path}",
                    reason="EXPECTED_CONSTRAINTS_INVALID",
                ) from error
        try:
            return cls(
                case_id=case_id,
                expected_intent=intent,
                expected_constraints=tuple(constraints),
            )
        except BenchmarkDataError as error:
            raise _prefix_error(error, path) from error

    def to_dict(self) -> dict[str, object]:
        intent = self.expected_intent.to_dict()
        intent.setdefault("spatial_constraints", [])
        return {
            "case_id": self.case_id,
            "expected_intent": intent,
            "expected_constraints": [
                constraint.to_dict() for constraint in self.expected_constraints
            ],
        }


@dataclass(frozen=True, slots=True)
class BenchmarkAnnotationSet:
    """Versioned reference labels bound to, but stored outside, one dataset."""

    annotation_set_id: str
    annotation_set_version: str
    dataset_id: str
    dataset_version: str
    annotations: tuple[ReferenceAnnotation, ...]
    schema_version: str = BENCHMARK_DATA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_identifier(
            self.annotation_set_id,
            path="/annotation_set_id",
            reason="ANNOTATION_SET_ID_INVALID",
        )
        _require_version(self.annotation_set_version, path="/annotation_set_version")
        _require_identifier(self.dataset_id, path="/dataset_id", reason="DATASET_ID_INVALID")
        _require_version(self.dataset_version, path="/dataset_version")
        if (
            not isinstance(self.annotations, tuple)
            or not 1 <= len(self.annotations) <= MAX_BENCHMARK_CASES
            or not all(type(value) is ReferenceAnnotation for value in self.annotations)
        ):
            raise _error(
                "Reference annotations must be a bounded immutable tuple.",
                path="/annotations",
                reason="ANNOTATIONS_INVALID",
            )
        if self.annotation_ids != tuple(sorted(set(self.annotation_ids))):
            raise _error(
                "Reference annotation case IDs must be sorted and unique.",
                path="/annotations",
                reason="ANNOTATION_IDS_NOT_SORTED_UNIQUE",
            )

    @property
    def annotation_ids(self) -> tuple[str, ...]:
        return tuple(annotation.case_id for annotation in self.annotations)

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_dict())

    def require_dataset(self, dataset: BenchmarkDataset) -> None:
        if type(dataset) is not BenchmarkDataset:
            raise _error(
                "Reference annotations require an exact BenchmarkDataset.",
                path="/dataset",
                reason="DATASET_TYPE_INVALID",
            )
        if (self.dataset_id, self.dataset_version) != (
            dataset.dataset_id,
            dataset.dataset_version,
        ):
            raise _error(
                "Reference annotations target a different dataset identity.",
                path="/dataset",
                reason="DATASET_IDENTITY_MISMATCH",
            )
        if self.annotation_ids != dataset.case_ids:
            raise _error(
                "Reference annotations must cover the dataset exactly once.",
                path="/annotations",
                reason="ANNOTATION_COVERAGE_MISMATCH",
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BenchmarkAnnotationSet:
        _require_fields(value, _ANNOTATION_SET_FIELDS, path="/")
        string_fields = {
            name: value.get(name)
            for name in (
                "schema_version",
                "annotation_set_id",
                "annotation_set_version",
                "dataset_id",
                "dataset_version",
            )
        }
        for name, field_value in string_fields.items():
            if not isinstance(field_value, str):
                raise _error(
                    f"Reference {name} must be a string.",
                    path=f"/{name}",
                    reason="FIELD_TYPE_INVALID",
                )
        annotation_values = value.get("annotations")
        if type(annotation_values) is not list:
            raise _error(
                "Reference annotations must be an array.",
                path="/annotations",
                reason="ANNOTATIONS_INVALID",
            )
        if not 1 <= len(annotation_values) <= MAX_BENCHMARK_CASES:
            raise _error(
                "Reference annotation count is outside the supported budget.",
                path="/annotations",
                reason="ANNOTATION_COUNT_INVALID",
            )
        annotations: list[ReferenceAnnotation] = []
        for index, annotation_value in enumerate(annotation_values):
            if type(annotation_value) is not dict:
                raise _error(
                    "Each reference annotation must be an object.",
                    path=f"/annotations/{index}",
                    reason="ANNOTATION_INVALID",
                )
            annotations.append(
                ReferenceAnnotation.from_dict(annotation_value, path=f"/annotations/{index}")
            )
        return cls(
            schema_version=cast(str, string_fields["schema_version"]),
            annotation_set_id=cast(str, string_fields["annotation_set_id"]),
            annotation_set_version=cast(str, string_fields["annotation_set_version"]),
            dataset_id=cast(str, string_fields["dataset_id"]),
            dataset_version=cast(str, string_fields["dataset_version"]),
            annotations=tuple(annotations),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "annotation_set_id": self.annotation_set_id,
            "annotation_set_version": self.annotation_set_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "annotations": [annotation.to_dict() for annotation in self.annotations],
        }


def load_benchmark_dataset(path: str | Path) -> BenchmarkDataset:
    """Load one bounded strict-JSON dataset into immutable typed values."""

    return BenchmarkDataset.from_dict(_load_json_object(path))


def load_benchmark_annotations(
    path: str | Path,
    *,
    dataset: BenchmarkDataset | None = None,
) -> BenchmarkAnnotationSet:
    """Load external labels and optionally require exact dataset coverage."""

    annotations = BenchmarkAnnotationSet.from_dict(_load_json_object(path))
    if dataset is not None:
        annotations.require_dataset(dataset)
    return annotations


def _load_json_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    with source.open("rb") as stream:
        raw = stream.read(MAX_BENCHMARK_FILE_BYTES + 1)
    if len(raw) > MAX_BENCHMARK_FILE_BYTES:
        raise _error(
            "Benchmark artifact exceeds the file byte budget.",
            path="/",
            reason="FILE_TOO_LARGE",
        )
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise _error(
            "Benchmark artifact must be UTF-8 encoded.",
            path="/",
            reason="UTF8_INVALID",
        ) from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
            parse_int=_bounded_int,
        )
    except _StrictJsonFailure as error:
        raise _error(
            "Benchmark artifact is not strict standard JSON.",
            path="/",
            reason=error.reason,
        ) from error
    except (json.JSONDecodeError, RecursionError) as error:
        raise _error(
            "Benchmark artifact is not valid JSON.",
            path="/",
            reason="JSON_INVALID",
        ) from error
    if type(value) is not dict:
        raise _error(
            "Benchmark artifact root must be an object.",
            path="/",
            reason="ROOT_TYPE_INVALID",
        )
    return cast(dict[str, Any], value)


class _StrictJsonFailure(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _StrictJsonFailure("DUPLICATE_OBJECT_MEMBER")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise _StrictJsonFailure("NON_STANDARD_NUMBER")


def _finite_float(value: str) -> float:
    if len(value) > _MAX_NUMBER_CHARACTERS:
        raise _StrictJsonFailure("NUMBER_OUT_OF_RANGE")
    try:
        parsed = float(value)
    except (OverflowError, ValueError) as error:
        raise _StrictJsonFailure("NUMBER_OUT_OF_RANGE") from error
    if not math.isfinite(parsed):
        raise _StrictJsonFailure("NON_STANDARD_NUMBER")
    return parsed


def _bounded_int(value: str) -> int:
    if len(value.lstrip("-")) > _MAX_NUMBER_CHARACTERS:
        raise _StrictJsonFailure("NUMBER_OUT_OF_RANGE")
    try:
        return int(value)
    except ValueError as error:
        raise _StrictJsonFailure("NUMBER_OUT_OF_RANGE") from error


def _require_fields(value: Mapping[str, Any], expected: set[str], *, path: str) -> None:
    if set(value) != expected:
        raise _error(
            "Benchmark object has missing or unexpected fields.",
            path=path,
            reason="FIELDS_INVALID",
        )


def _require_schema_version(value: object) -> None:
    if value != BENCHMARK_DATA_SCHEMA_VERSION:
        raise _error(
            "Unsupported benchmark data schema version.",
            path="/schema_version",
            reason="SCHEMA_VERSION_UNSUPPORTED",
        )


def _require_version(value: object, *, path: str) -> None:
    if not isinstance(value, str) or _VERSION_PATTERN.fullmatch(value) is None:
        raise _error(
            "Benchmark version must be canonical semantic version text.",
            path=path,
            reason="VERSION_INVALID",
        )


def _require_identifier(value: object, *, path: str, reason: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise _error(
            "Benchmark identifier must be a canonical lowercase token.",
            path=path,
            reason=reason,
        )


def _canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise _error(
            "Benchmark value cannot be encoded as canonical JSON.",
            path="/",
            reason="CANONICAL_JSON_INVALID",
        ) from error
    return hashlib.sha256(encoded).hexdigest()


def _error(message: str, *, path: str, reason: str) -> BenchmarkDataError:
    return BenchmarkDataError(message, path=path, reason=reason)


def _prefix_error(error: BenchmarkDataError, prefix: str) -> BenchmarkDataError:
    return BenchmarkDataError(
        str(error),
        path=f"{prefix}{error.path}",
        reason=error.reason,
    )


__all__ = [
    "BENCHMARK_DATA_SCHEMA_VERSION",
    "MAX_BENCHMARK_CASES",
    "MAX_BENCHMARK_FILE_BYTES",
    "MAX_REQUIREMENT_BYTES",
    "BenchmarkAnnotationSet",
    "BenchmarkCase",
    "BenchmarkDataError",
    "BenchmarkDataset",
    "ReferenceAnnotation",
    "load_benchmark_annotations",
    "load_benchmark_dataset",
]
