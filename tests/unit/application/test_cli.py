from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_parametric_architect.cli import main


def _write_model(path: Path, model: dict[str, Any]) -> None:
    path.write_text(json.dumps(model), encoding="utf-8")


def test_validate_command_prints_machine_readable_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    valid_simple_house: dict[str, Any],
) -> None:
    model_path = tmp_path / "house.json"
    _write_model(model_path, valid_simple_house)

    exit_code = main(["validate", str(model_path)])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["valid"] is True


def test_validate_command_uses_nonzero_exit_for_issues(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    invalid_overlap: dict[str, Any],
) -> None:
    model_path = tmp_path / "overlap.json"
    _write_model(model_path, invalid_overlap)

    exit_code = main(["validate", str(model_path)])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert report["issues"][0]["code"] == "ROOM_OVERLAP"


def test_render_command_writes_svg(tmp_path: Path, valid_simple_house: dict[str, Any]) -> None:
    model_path = tmp_path / "house.json"
    output_path = tmp_path / "house.svg"
    _write_model(model_path, valid_simple_house)

    exit_code = main(["render-svg", str(model_path), str(output_path)])

    assert exit_code == 0
    assert output_path.read_text(encoding="utf-8").startswith("<svg")


def test_render_command_refuses_invalid_model(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    invalid_opening: dict[str, Any],
) -> None:
    model_path = tmp_path / "invalid.json"
    output_path = tmp_path / "invalid.svg"
    _write_model(model_path, invalid_opening)

    exit_code = main(["render-svg", str(model_path), str(output_path)])
    error_report = json.loads(capsys.readouterr().err)

    assert exit_code == 1
    assert not output_path.exists()
    assert any(issue["code"] == "OPENING_OUT_OF_WALL_BOUNDS" for issue in error_report["issues"])


def test_cli_reports_missing_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["validate", str(tmp_path / "missing.json")])

    assert exit_code == 2
    assert "No such file" in capsys.readouterr().err


def test_cli_reports_unknown_floor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    valid_simple_house: dict[str, Any],
) -> None:
    model_path = tmp_path / "house.json"
    output_path = tmp_path / "house.svg"
    _write_model(model_path, valid_simple_house)

    exit_code = main(
        [
            "render-svg",
            str(model_path),
            str(output_path),
            "--floor-id",
            "flr_missing",
        ]
    )

    assert exit_code == 2
    assert "flr_missing" in capsys.readouterr().err
