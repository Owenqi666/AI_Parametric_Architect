from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ai_parametric_architect.benchmark import (
    load_benchmark_annotations,
    load_benchmark_dataset,
)
from ai_parametric_architect.showcase_generation import (
    BENCHMARK_ANNOTATIONS,
    BENCHMARK_DATASET,
    BENCHMARK_TRIALS,
    DEFAULT_BENCHMARK_OUTPUT,
    DEFAULT_PREVIEW_OUTPUT,
    build_preview_artifact,
)


def _object(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_checked_in_preview_is_exactly_the_deterministic_pipeline_output() -> None:
    expected = build_preview_artifact().to_dict()
    actual = _object(DEFAULT_PREVIEW_OUTPUT)

    assert actual == expected


def test_checked_in_benchmark_report_is_bound_to_standard_inputs_and_two_trials() -> None:
    dataset = load_benchmark_dataset(BENCHMARK_DATASET)
    annotations = load_benchmark_annotations(BENCHMARK_ANNOTATIONS, dataset=dataset)
    report = _object(DEFAULT_BENCHMARK_OUTPUT)
    report_dataset = cast(dict[str, Any], report["dataset"])
    report_annotations = cast(dict[str, Any], report["annotations"])
    configuration = cast(dict[str, Any], report["configuration"])
    systems = cast(list[dict[str, Any]], report["systems"])

    assert report["schema_version"] == "1.0.0"
    assert report_dataset == {
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "digest": dataset.digest,
        "case_count": len(dataset.cases),
    }
    assert report_annotations == {
        "annotation_set_id": annotations.annotation_set_id,
        "annotation_set_version": annotations.annotation_set_version,
        "digest": annotations.digest,
    }
    assert configuration["trials"] == BENCHMARK_TRIALS
    assert [value["descriptor"]["system_id"] for value in systems] == [
        "rule-spatial-v2",
        "cp-sat-v2",
    ]
    assert len(cast(list[object], report["observations"])) == (
        len(dataset.cases) * len(systems) * BENCHMARK_TRIALS
    )


def test_checked_in_benchmark_truthfully_separates_parser_and_cp_sat_results() -> None:
    report = _object(DEFAULT_BENCHMARK_OUTPUT)
    systems = cast(list[dict[str, Any]], report["systems"])
    cp_sat = next(value for value in systems if value["descriptor"]["system_id"] == "cp-sat-v2")
    tracks = cast(dict[str, dict[str, Any]], cp_sat["tracks"])
    end_to_end = cast(dict[str, dict[str, Any]], tracks["end_to_end"]["metrics"])
    oracle = cast(dict[str, dict[str, Any]], tracks["oracle_intent"]["metrics"])

    assert cp_sat["intent_extraction_accuracy"]["value"] == 0.0
    assert end_to_end["planning_success"]["value"] == 1.0
    assert end_to_end["plan_validity"]["value"] == 0.0
    assert end_to_end["constraint_satisfaction"]["applicable"] is False
    assert end_to_end["constraint_satisfaction"]["reason"] == (
        "EXACT_REFERENCE_INTENT_REQUIRED"
    )
    assert oracle["planning_success"]["value"] == 1.0
    assert oracle["plan_validity"]["value"] == 1.0
    assert oracle["constraint_satisfaction"]["value"] == 1.0
    assert oracle["stability"]["value"] == 1.0
