from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from ai_parametric_architect.backend import create_app

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client


async def test_health_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_validate_endpoint_returns_stable_report(
    client: httpx.AsyncClient, valid_simple_house: dict[str, Any]
) -> None:
    response = await client.post("/v1/models/validate", json=valid_simple_house)

    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "model_id": "mdl_simple_house",
        "revision": 0,
        "error_count": 0,
        "issues": [],
    }


async def test_validate_endpoint_reports_room_overlap(
    client: httpx.AsyncClient, invalid_overlap: dict[str, Any]
) -> None:
    response = await client.post("/v1/models/validate", json=invalid_overlap)

    body = response.json()
    assert response.status_code == 200
    assert body["valid"] is False
    assert [issue["code"] for issue in body["issues"]] == ["ROOM_OVERLAP"]


async def test_render_endpoint_returns_deterministic_svg(
    client: httpx.AsyncClient, valid_simple_house: dict[str, Any]
) -> None:
    first = await client.post("/v1/models/render/svg", json=valid_simple_house)
    second = await client.post("/v1/models/render/svg", json=valid_simple_house)

    assert first.status_code == 200
    assert first.headers["content-type"].startswith("image/svg+xml")
    assert first.content == second.content


async def test_render_endpoint_returns_machine_readable_validation_error(
    client: httpx.AsyncClient, invalid_opening: dict[str, Any]
) -> None:
    response = await client.post("/v1/models/render/svg", json=invalid_opening)

    body = response.json()
    assert response.status_code == 422
    assert body["valid"] is False
    issue = next(item for item in body["issues"] if item["code"] == "OPENING_OUT_OF_WALL_BOUNDS")
    assert set(issue) == {"code", "severity", "path", "entity_ids", "message", "details"}
    assert issue["severity"] == "error"


async def test_render_endpoint_returns_structured_floor_error(
    client: httpx.AsyncClient, valid_simple_house: dict[str, Any]
) -> None:
    response = await client.post(
        "/v1/models/render/svg?floor_id=flr_missing", json=valid_simple_house
    )

    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "RENDER_FLOOR_NOT_FOUND"


async def test_non_object_request_returns_unified_issue_shape(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/models/validate", json=["not", "a", "model"])

    body = response.json()
    assert response.status_code == 422
    assert body["issues"][0]["code"] == "REQUEST_INVALID"
    assert body["error_count"] == 1


async def test_render_endpoint_rejects_floor_without_geometry(
    client: httpx.AsyncClient, valid_simple_house: dict[str, Any]
) -> None:
    for registry_name in ("rooms", "walls", "doors", "windows", "stairs"):
        valid_simple_house["entities"][registry_name] = {}

    response = await client.post("/v1/models/render/svg", json=valid_simple_house)

    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "RENDER_NO_GEOMETRY"


async def test_validate_endpoint_handles_out_of_float_range_json_number(
    client: httpx.AsyncClient, valid_simple_house: dict[str, Any]
) -> None:
    valid_simple_house["entities"]["walls"]["wal_south"]["axis"]["end"][0] = 10**400

    response = await client.post("/v1/models/validate", json=valid_simple_house)

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert any(
        issue["code"] == "MODEL_COORDINATE_RANGE_EXCEEDED" for issue in response.json()["issues"]
    )
