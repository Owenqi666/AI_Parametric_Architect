from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ai_parametric_architect.benchmark.cli as benchmark_cli
from ai_parametric_architect.benchmark.cli import main
from ai_parametric_architect.infrastructure import OpenAIProviderConfig


class _Report:
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": "test", "systems": []}


class _Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object, tuple[object, ...], int]] = []

    def run(
        self,
        dataset: object,
        annotations: object,
        systems: tuple[object, ...],
        *,
        trials: int,
    ) -> _Report:
        self.calls.append((dataset, annotations, systems, trials))
        return _Report()


def _artifacts(tmp_path: Path) -> tuple[Path, Path]:
    dataset = tmp_path / "dataset.json"
    annotations = tmp_path / "annotations.json"
    dataset.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "dataset_id": "cli-dataset",
                "dataset_version": "1.0.0",
                "cases": [
                    {
                        "case_id": "cli_case",
                        "tags": ["cli"],
                        "input_requirement": "Design a 20 sqm house with one study.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    annotations.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "annotation_set_id": "cli-reference",
                "annotation_set_version": "1.0.0",
                "dataset_id": "cli-dataset",
                "dataset_version": "1.0.0",
                "annotations": [
                    {
                        "case_id": "cli_case",
                        "expected_intent": {
                            "building_type": "house",
                            "area": 20,
                            "rooms": ["study"],
                            "orientation": None,
                            "spatial_constraints": [],
                        },
                        "expected_constraints": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return dataset, annotations


def test_cli_runs_offline_systems_by_default_without_openai(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset, annotations = _artifacts(tmp_path)
    output = tmp_path / "report.json"
    runner = _Runner()
    openai_calls: list[object] = []
    rule_system = object()
    cp_sat_system = object()
    monkeypatch.setattr(benchmark_cli, "create_planning_benchmark_runner", lambda **_: runner)
    monkeypatch.setattr(
        benchmark_cli,
        "create_rule_spatial_benchmark_system",
        lambda: rule_system,
    )
    monkeypatch.setattr(
        benchmark_cli,
        "create_cp_sat_benchmark_system",
        lambda **_: cp_sat_system,
    )
    monkeypatch.setattr(
        benchmark_cli,
        "create_openai_cp_sat_benchmark_system",
        lambda *args, **kwargs: openai_calls.append((args, kwargs)),
    )

    exit_code = main([str(dataset), str(annotations), str(output), "--trials", "2"])

    assert exit_code == 0
    assert openai_calls == []
    assert runner.calls[0][2] == (rule_system, cp_sat_system)
    assert runner.calls[0][3] == 2
    assert json.loads(output.read_text(encoding="utf-8")) == _Report().to_dict()


def test_cli_requires_explicit_model_and_passes_no_api_key_argument(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset, annotations = _artifacts(tmp_path)
    output = tmp_path / "report.json"
    runner = _Runner()
    received: list[tuple[OpenAIProviderConfig, dict[str, Any]]] = []
    monkeypatch.setattr(benchmark_cli, "create_planning_benchmark_runner", lambda **_: runner)
    monkeypatch.setattr(benchmark_cli, "create_rule_spatial_benchmark_system", object)
    monkeypatch.setattr(benchmark_cli, "create_cp_sat_benchmark_system", lambda **_: object())

    def create_openai(
        config: OpenAIProviderConfig,
        **kwargs: Any,
    ) -> object:
        received.append((config, kwargs))
        return object()

    monkeypatch.setattr(benchmark_cli, "create_openai_cp_sat_benchmark_system", create_openai)

    exit_code = main(
        [
            str(dataset),
            str(annotations),
            str(output),
            "--openai-model",
            "gpt-test",
        ]
    )

    assert exit_code == 0
    assert received[0][0].model == "gpt-test"
    assert not hasattr(received[0][0], "api_key")
    assert len(runner.calls[0][2]) == 3


def test_cli_reports_data_errors_without_creating_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "report.json"

    exit_code = main(
        [
            str(tmp_path / "missing-dataset.json"),
            str(tmp_path / "missing-annotations.json"),
            str(output),
        ]
    )

    assert exit_code == 2
    assert not output.exists()
    assert "missing-dataset.json" in capsys.readouterr().err


def test_cli_refuses_to_overwrite_an_input_artifact_before_running(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset, annotations = _artifacts(tmp_path)
    before = dataset.read_bytes()

    exit_code = main([str(dataset), str(annotations), str(dataset)])

    assert exit_code == 2
    assert dataset.read_bytes() == before
    assert "must not overwrite" in capsys.readouterr().err
