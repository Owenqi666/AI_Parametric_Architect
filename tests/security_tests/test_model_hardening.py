from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from ai_parametric_architect.backend.api import create_app
from ai_parametric_architect.domain import (
    InvalidPatchError,
    ModelComplexityPolicy,
    PatchOperation,
)
from ai_parametric_architect.editing import JsonPatchEngine
from ai_parametric_architect.geometry_engine import ShapelyGeometryEngine
from ai_parametric_architect.renderer import SvgRenderer, WorldModelRenderIRProjector
from ai_parametric_architect.validation import ModelValidator

PROJECT_ROOT = Path(__file__).parents[2]


def model() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((PROJECT_ROOT / "examples" / "valid_simple_house.json").read_text()),
    )


@pytest.mark.parametrize(
    ("invalid_root", "expected_code"),
    [
        ([], "SCHEMA_TYPE"),
        ((), "JSON_TREE_INVALID"),
        ({"not-json"}, "JSON_TREE_INVALID"),
        (object(), "JSON_TREE_INVALID"),
    ],
)
def test_validator_rejects_non_document_roots_without_crashing(
    invalid_root: object,
    expected_code: str,
) -> None:
    report = ModelValidator(ShapelyGeometryEngine()).validate(cast(Any, invalid_root))

    assert not report.valid
    assert report.model_id is None
    assert report.issues[0].code == expected_code


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_standard_json_numbers_are_structurally_rejected_by_both_api_paths(
    constant: str,
) -> None:
    value = model()
    value["metadata"]["unsafe"] = 0
    raw = json.dumps(value).replace('"unsafe": 0', f'"unsafe": {constant}')
    client = TestClient(create_app(), raise_server_exceptions=False)

    validation = client.post(
        "/v1/models/validate",
        content=raw,
        headers={"content-type": "application/json"},
    )
    rendering = client.post(
        "/v1/models/render/svg",
        content=raw,
        headers={"content-type": "application/json"},
    )
    render_ir = client.post(
        "/v1/models/render/ir",
        content=raw,
        headers={"content-type": "application/json"},
    )

    assert validation.status_code == 200
    assert validation.json()["valid"] is False
    assert validation.json()["issues"][0]["code"] == "JSON_TREE_INVALID"
    assert rendering.status_code == 422
    assert rendering.json()["issues"][0]["code"] == "JSON_TREE_INVALID"
    assert render_ir.status_code == 422
    assert render_ir.json()["issues"][0]["code"] == "JSON_TREE_INVALID"


def test_huge_but_finite_geometry_is_rejected_before_derived_overflow() -> None:
    value = model()
    value["entities"]["walls"]["wal_south"]["thickness"] = 1.7e308

    report = ModelValidator(ShapelyGeometryEngine()).validate(value)

    assert not report.valid
    assert tuple(issue.code for issue in report.issues) == ("MODEL_COORDINATE_RANGE_EXCEEDED",)


def test_huge_opening_is_a_structured_validation_error_not_a_transport_500() -> None:
    value = model()
    value["entities"]["windows"]["win_south"]["width"] = 1.7e308
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post("/v1/models/render/svg", json=value)

    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "MODEL_COORDINATE_RANGE_EXCEEDED"
    assert math.isfinite(float(response.headers["content-length"]))
    assert "Infinity" not in response.text
    assert "NaN" not in response.text


def test_renderer_never_serializes_inf_or_nan_for_extreme_direct_input() -> None:
    value = model()
    value["entities"]["walls"]["wal_south"]["thickness"] = 1.7e308
    renderer = SvgRenderer(ShapelyGeometryEngine())

    with pytest.raises(ValueError, match="finite"):
        renderer.render(value)

    ordinary_svg = renderer.render(model()).lower()
    assert "inf" not in ordinary_svg
    assert "nan" not in ordinary_svg


def test_render_ir_never_exposes_non_finite_direct_or_derived_coordinates() -> None:
    value = model()
    value["coordinate_system"]["origin"][2] = math.inf
    projector = WorldModelRenderIRProjector(ShapelyGeometryEngine())

    with pytest.raises(ValueError, match="finite"):
        projector.project(value)

    ordinary = json.dumps(projector.project(model()).to_dict(), allow_nan=False).lower()
    assert "infinity" not in ordinary
    assert "nan" not in ordinary


def test_render_ir_names_remain_json_data_not_html_transport() -> None:
    value = model()
    value["entities"]["rooms"]["rom_living"]["name"] = '<img src=x onerror="alert(1)">'
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post("/v1/models/render/ir", json=value)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["objects"][0]["name"] == '<img src=x onerror="alert(1)">'


def test_oversized_entity_and_polygon_models_are_rejected_deterministically() -> None:
    value = model()
    before = copy.deepcopy(value)
    entity_report = ModelValidator(
        ShapelyGeometryEngine(),
        complexity_policy=ModelComplexityPolicy(max_total_entities=1),
    ).validate(value)
    vertex_report = ModelValidator(
        ShapelyGeometryEngine(),
        complexity_policy=ModelComplexityPolicy(max_polygon_vertices=4),
    ).validate(value)

    assert entity_report.issues[0].code == "MODEL_ENTITY_LIMIT_EXCEEDED"
    assert vertex_report.issues[0].code == "MODEL_POLYGON_VERTEX_LIMIT_EXCEEDED"
    assert value == before


def test_patch_operation_budget_is_enforced_by_patch_adapter() -> None:
    engine = JsonPatchEngine(
        complexity_policy=ModelComplexityPolicy(max_patch_operations=1),
    )

    with pytest.raises(InvalidPatchError) as error:
        engine.apply(
            {},
            (
                PatchOperation("add", "/first", 1),
                PatchOperation("add", "/second", 2),
            ),
        )

    assert error.value.details["reason"] == "PATCH_OPERATION_LIMIT_EXCEEDED"
