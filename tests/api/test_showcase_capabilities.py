from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from ai_parametric_architect.backend import PublicCapabilities, create_app

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _client(
    capabilities: PublicCapabilities | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(capabilities=capabilities))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_public_capabilities_default_to_false() -> None:
    async for client in _client():
        response = await client.get("/v1/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "openai_requirement_parser_available": False,
        "benchmark_live_mode_available": False,
        "live_planning_preview_available": False,
    }


async def test_public_capabilities_are_not_inferred_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "sk-environment-marker-must-not-be-public"
    monkeypatch.setenv("OPENAI_API_KEY", marker)
    monkeypatch.setenv("BENCHMARK_LIVE_MODE", "true")
    monkeypatch.setenv("LIVE_PLANNING_PREVIEW", "true")

    async for client in _client():
        response = await client.get("/v1/capabilities")

    assert response.json() == {
        "openai_requirement_parser_available": False,
        "benchmark_live_mode_available": False,
        "live_planning_preview_available": False,
    }
    assert marker not in response.text


async def test_public_capabilities_require_explicit_trusted_configuration() -> None:
    configured = PublicCapabilities(
        openai_requirement_parser_available=True,
        benchmark_live_mode_available=True,
        live_planning_preview_available=False,
    )

    async for client in _client(configured):
        response = await client.get("/v1/capabilities")

    assert response.json() == {
        "openai_requirement_parser_available": True,
        "benchmark_live_mode_available": True,
        "live_planning_preview_available": False,
    }


def test_public_capabilities_reject_non_boolean_values() -> None:
    with pytest.raises(TypeError, match="exact boolean"):
        PublicCapabilities(openai_requirement_parser_available=1)  # type: ignore[arg-type]
