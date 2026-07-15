from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest

from ai_parametric_architect.benchmark import (
    MAX_BENCHMARK_CASES,
    MAX_BENCHMARK_FILE_BYTES,
    MAX_REQUIREMENT_BYTES,
    BenchmarkCase,
    BenchmarkDataError,
    load_benchmark_annotations,
    load_benchmark_dataset,
)
from ai_parametric_architect.planning import (
    SOLVED_FLOOR_PLAN_SCHEMA_VERSION,
    RuleBasedRequirementParser,
)
from ai_parametric_architect.planning.solver import ConstraintFloorPlanPlanner

ROOT = Path(__file__).parents[3]
DATASET_PATH = ROOT / "benchmarks" / "datasets" / "planning-core-1.0.0.json"
ANNOTATIONS_PATH = ROOT / "benchmarks" / "annotations" / "planning-core-reference-1.0.0.json"


def _payload(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def test_packaged_core_artifacts_are_bilingual_complete_and_digest_stable() -> None:
    dataset = load_benchmark_dataset(DATASET_PATH)
    annotations = load_benchmark_annotations(ANNOTATIONS_PATH, dataset=dataset)

    assert len(dataset.cases) == len(annotations.annotations) == 8
    assert dataset.case_ids == annotations.annotation_ids
    assert dataset.digest == "e5c2c55263efe794db4aaf72064946a841b9648dedab896f7c2275556cba4017"
    assert annotations.digest == "3035ca7af6bdadf7029da653b7a6125da950c4fbbaa267c3d60cd8116253f84e"
    assert any("设计" in case.input_requirement for case in dataset.cases)
    assert any("Design" in case.input_requirement for case in dataset.cases)
    relations = {
        constraint.relation.value
        for annotation in annotations.annotations
        for constraint in annotation.expected_constraints
    }
    assert {
        "adjacent_to",
        "east_of",
        "near",
        "north_of",
        "separated_from",
        "west_of",
    }.issubset(relations)


def test_fixture_isolates_the_rule_parsers_known_spatial_constraint_gap() -> None:
    dataset = load_benchmark_dataset(DATASET_PATH)
    annotations = load_benchmark_annotations(ANNOTATIONS_PATH, dataset=dataset)
    parser = RuleBasedRequirementParser()

    for case, annotation in zip(dataset.cases, annotations.annotations, strict=True):
        parsed = parser.parse(case.input_requirement)
        expected = annotation.expected_intent

        assert (
            parsed.building_type,
            parsed.area,
            parsed.rooms,
            parsed.orientation,
        ) == (
            expected.building_type,
            expected.area,
            expected.rooms,
            expected.orientation,
        )
        assert parsed.spatial_constraints == ()
        assert expected.spatial_constraints


def test_reference_intents_are_feasible_detached_cp_sat_inputs() -> None:
    dataset = load_benchmark_dataset(DATASET_PATH)
    annotations = load_benchmark_annotations(ANNOTATIONS_PATH, dataset=dataset)
    planner = ConstraintFloorPlanPlanner()

    proposals = tuple(
        planner.plan(annotation.expected_intent) for annotation in annotations.annotations
    )

    assert len(proposals) == len(dataset.cases)
    assert all(plan.schema_version == SOLVED_FLOOR_PLAN_SCHEMA_VERSION for plan in proposals)
    assert all(
        plan.intent == annotation.expected_intent
        for plan, annotation in zip(proposals, annotations.annotations, strict=True)
    )


def test_loaded_values_are_deeply_defensive_and_have_no_world_state_fields() -> None:
    dataset = load_benchmark_dataset(DATASET_PATH)
    annotations = load_benchmark_annotations(ANNOTATIONS_PATH, dataset=dataset)
    dataset_payload = dataset.to_dict()
    annotation_payload = annotations.to_dict()

    cast(list[dict[str, Any]], dataset_payload["cases"])[0]["input_requirement"] = "changed"
    cast(list[dict[str, Any]], dataset_payload["cases"])[0]["tags"] = ["changed"]
    cast(list[dict[str, Any]], annotation_payload["annotations"])[0]["expected_intent"] = {
        "changed": True
    }

    assert dataset.cases[0].input_requirement != "changed"
    assert dataset.cases[0].tags != ("changed",)
    assert annotations.annotations[0].expected_intent.building_type == "house"
    assert not hasattr(dataset, "__dict__")
    assert not hasattr(annotations, "__dict__")
    with pytest.raises(FrozenInstanceError):
        dataset.dataset_id = "changed"  # type: ignore[misc]
    serialized = json.dumps(
        {"dataset": dataset.to_dict(), "annotations": annotations.to_dict()},
        ensure_ascii=False,
    )
    for forbidden in ("world_model", "model_id", "revision", "document", "geometry"):
        assert forbidden not in serialized


def test_digest_uses_canonical_typed_content_not_json_formatting(tmp_path: Path) -> None:
    compact_path = tmp_path / "compact.json"
    compact_path.write_text(
        json.dumps(_payload(DATASET_PATH), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    first = load_benchmark_dataset(DATASET_PATH)
    second = load_benchmark_dataset(compact_path)

    assert second == first
    assert second.digest == first.digest
    assert second.to_dict() is not first.to_dict()


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_loader_rejects_non_standard_or_non_finite_numbers(
    tmp_path: Path,
    constant: str,
) -> None:
    path = tmp_path / "non-standard.json"
    path.write_text(f'{{"value":{constant}}}', encoding="utf-8")

    with pytest.raises(BenchmarkDataError) as captured:
        load_benchmark_dataset(path)

    assert captured.value.reason == "NON_STANDARD_NUMBER"


def test_loader_rejects_duplicate_members_invalid_utf8_and_oversize_files(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":"1.0.0","schema_version":"1.0.0"}',
        encoding="utf-8",
    )
    invalid_utf8 = tmp_path / "invalid-utf8.json"
    invalid_utf8.write_bytes(b"\xff")
    oversize = tmp_path / "oversize.json"
    oversize.write_bytes(b" " * (MAX_BENCHMARK_FILE_BYTES + 1))

    for path, reason in (
        (duplicate, "DUPLICATE_OBJECT_MEMBER"),
        (invalid_utf8, "UTF8_INVALID"),
        (oversize, "FILE_TOO_LARGE"),
    ):
        with pytest.raises(BenchmarkDataError) as captured:
            load_benchmark_dataset(path)
        assert captured.value.reason == reason


def test_loader_rejects_huge_numeric_values_before_domain_conversion(tmp_path: Path) -> None:
    path = tmp_path / "huge-number.json"
    text = ANNOTATIONS_PATH.read_text(encoding="utf-8")
    text = text.replace('"area": 80', f'"area": {"9" * 512}', 1)
    path.write_text(text, encoding="utf-8")

    with pytest.raises(BenchmarkDataError) as captured:
        load_benchmark_annotations(path)

    assert captured.value.reason == "NUMBER_OUT_OF_RANGE"


def test_dataset_rejects_extra_fields_bad_versions_and_noncanonical_order(
    tmp_path: Path,
) -> None:
    def assert_rejected(payload: dict[str, Any], reason: str, index: int) -> None:
        path = tmp_path / f"invalid-{index}.json"
        _write(path, payload)
        with pytest.raises(BenchmarkDataError) as captured:
            load_benchmark_dataset(path)
        assert captured.value.reason == reason

    values: list[tuple[dict[str, Any], str]] = []

    extra_root = _payload(DATASET_PATH)
    extra_root["world_model"] = {}
    values.append((extra_root, "FIELDS_INVALID"))

    extra_case = _payload(DATASET_PATH)
    extra_case["cases"][0]["revision"] = 1
    values.append((extra_case, "FIELDS_INVALID"))

    bad_schema = _payload(DATASET_PATH)
    bad_schema["schema_version"] = "2.0.0"
    values.append((bad_schema, "SCHEMA_VERSION_UNSUPPORTED"))

    bad_version = _payload(DATASET_PATH)
    bad_version["dataset_version"] = "01.0.0"
    values.append((bad_version, "VERSION_INVALID"))

    unsorted_cases = _payload(DATASET_PATH)
    unsorted_cases["cases"].reverse()
    values.append((unsorted_cases, "CASE_IDS_NOT_SORTED_UNIQUE"))

    duplicate_case = _payload(DATASET_PATH)
    duplicate_case["cases"][1] = deepcopy(duplicate_case["cases"][0])
    values.append((duplicate_case, "CASE_IDS_NOT_SORTED_UNIQUE"))

    unsorted_tags = _payload(DATASET_PATH)
    unsorted_tags["cases"][0]["tags"].reverse()
    values.append((unsorted_tags, "TAGS_NOT_SORTED_UNIQUE"))

    duplicate_tags = _payload(DATASET_PATH)
    duplicate_tags["cases"][0]["tags"].append("residential")
    values.append((duplicate_tags, "TAGS_NOT_SORTED_UNIQUE"))

    for index, (payload, reason) in enumerate(values):
        assert_rejected(payload, reason, index)


def test_dataset_enforces_case_and_requirement_budgets(tmp_path: Path) -> None:
    maximum_requirement = BenchmarkCase(
        case_id="budget_exact",
        tags=("budget",),
        input_requirement="a" * MAX_REQUIREMENT_BYTES,
    )
    assert len(maximum_requirement.input_requirement.encode("utf-8")) == MAX_REQUIREMENT_BYTES

    too_long = _payload(DATASET_PATH)
    too_long["cases"][0]["input_requirement"] = "界" * (MAX_REQUIREMENT_BYTES // 3 + 1)
    too_long_path = tmp_path / "too-long.json"
    _write(too_long_path, too_long)
    with pytest.raises(BenchmarkDataError) as requirement_error:
        load_benchmark_dataset(too_long_path)
    assert requirement_error.value.reason == "REQUIREMENT_TOO_LARGE"

    too_many = _payload(DATASET_PATH)
    template = deepcopy(too_many["cases"][0])
    too_many["cases"] = [
        {**template, "case_id": f"budget_case_{index:03d}"}
        for index in range(MAX_BENCHMARK_CASES + 1)
    ]
    too_many_path = tmp_path / "too-many.json"
    _write(too_many_path, too_many)
    with pytest.raises(BenchmarkDataError) as count_error:
        load_benchmark_dataset(too_many_path)
    assert count_error.value.reason == "CASE_COUNT_INVALID"


def test_annotation_loader_rejects_extra_fields_order_duplicates_and_mismatch(
    tmp_path: Path,
) -> None:
    dataset = load_benchmark_dataset(DATASET_PATH)

    def assert_rejected(payload: dict[str, Any], reason: str, index: int) -> None:
        path = tmp_path / f"invalid-annotation-{index}.json"
        _write(path, payload)
        with pytest.raises(BenchmarkDataError) as captured:
            load_benchmark_annotations(path, dataset=dataset)
        assert captured.value.reason == reason

    values: list[tuple[dict[str, Any], str]] = []

    extra = _payload(ANNOTATIONS_PATH)
    extra["annotations"][0]["model_revision"] = 3
    values.append((extra, "FIELDS_INVALID"))

    unsorted = _payload(ANNOTATIONS_PATH)
    unsorted["annotations"].reverse()
    values.append((unsorted, "ANNOTATION_IDS_NOT_SORTED_UNIQUE"))

    duplicate = _payload(ANNOTATIONS_PATH)
    duplicate["annotations"][1] = deepcopy(duplicate["annotations"][0])
    values.append((duplicate, "ANNOTATION_IDS_NOT_SORTED_UNIQUE"))

    constraint_mismatch = _payload(ANNOTATIONS_PATH)
    constraint_mismatch["annotations"][0]["expected_constraints"] = []
    values.append((constraint_mismatch, "EXPECTED_CONSTRAINTS_MISMATCH"))

    wrong_dataset = _payload(ANNOTATIONS_PATH)
    wrong_dataset["dataset_version"] = "1.0.1"
    values.append((wrong_dataset, "DATASET_IDENTITY_MISMATCH"))

    missing = _payload(ANNOTATIONS_PATH)
    missing["annotations"].pop()
    values.append((missing, "ANNOTATION_COVERAGE_MISMATCH"))

    for index, (payload, reason) in enumerate(values):
        assert_rejected(payload, reason, index)


def test_expected_intent_shape_is_canonical_and_strict(tmp_path: Path) -> None:
    payload = _payload(ANNOTATIONS_PATH)
    payload["annotations"][0]["expected_intent"]["repository"] = "forbidden"
    path = tmp_path / "intent-extra.json"
    _write(path, payload)

    with pytest.raises(BenchmarkDataError) as captured:
        load_benchmark_annotations(path)

    assert captured.value.reason == "FIELDS_INVALID"
    assert captured.value.path == "/annotations/0/expected_intent"
