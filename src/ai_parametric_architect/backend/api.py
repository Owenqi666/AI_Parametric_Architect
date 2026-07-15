"""FastAPI transport adapter."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Body, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from ai_parametric_architect import __version__
from ai_parametric_architect.application import ArchitectService, ModelValidationError
from ai_parametric_architect.composition import create_service
from ai_parametric_architect.domain import (
    Severity,
    StrictJsonTreeGuard,
    ValidationIssue,
    ValidationReport,
)
from ai_parametric_architect.ports import FloorNotFoundError, NoRenderableGeometryError

from .capabilities import PublicCapabilities
from .request_limits import RequestBodySizeLimitMiddleware, RequestBodySizePolicy


def _json_pointer(parts: tuple[object, ...]) -> str:
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped) if escaped else "/"


def _transport_error(code: str, message: str, path: str) -> dict[str, Any]:
    issue = ValidationIssue(
        code=code,
        severity=Severity.ERROR,
        message=message,
        path=path,
    )
    return ValidationReport.create({}, (issue,)).to_dict()


def create_app(
    service: ArchitectService | None = None,
    *,
    capabilities: PublicCapabilities | None = None,
    json_guard: StrictJsonTreeGuard | None = None,
    request_body_policy: RequestBodySizePolicy | None = None,
) -> FastAPI:
    application = create_service() if service is None else service
    public_capabilities = PublicCapabilities() if capabilities is None else capabilities
    if type(public_capabilities) is not PublicCapabilities:
        raise TypeError("capabilities must be an exact PublicCapabilities value.")
    strict_json = StrictJsonTreeGuard() if json_guard is None else json_guard
    app = FastAPI(title="AI Parametric Architect", version=__version__)
    app.add_middleware(RequestBodySizeLimitMiddleware, policy=request_body_policy)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        location = errors[0].get("loc", ()) if errors else ()
        pointer_parts = tuple(part for part in location if part != "body")
        return JSONResponse(
            status_code=422,
            content=_transport_error(
                "REQUEST_INVALID",
                "Request body must be a valid JSON model object.",
                _json_pointer(pointer_parts),
            ),
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "ai-parametric-architect", "version": __version__}

    @app.get("/v1/capabilities")
    def capabilities_endpoint() -> dict[str, bool]:
        return public_capabilities.to_dict()

    @app.post("/v1/models/validate")
    def validate_model(model: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        json_issue = strict_json.issue(model)
        if json_issue is not None:
            return ValidationReport.create(model, (json_issue,)).to_dict()
        return application.validate(model).to_dict()

    @app.post("/v1/models/render/svg")
    def render_svg(
        model: Annotated[dict[str, Any], Body()],
        floor_id: Annotated[str | None, Query()] = None,
    ) -> Response:
        json_issue = strict_json.issue(model)
        if json_issue is not None:
            report = ValidationReport.create(model, (json_issue,))
            return JSONResponse(status_code=422, content=report.to_dict())
        try:
            svg = application.render_svg(model, floor_id)
        except ModelValidationError as exc:
            return JSONResponse(status_code=422, content=exc.report.to_dict())
        except FloorNotFoundError as exc:
            return JSONResponse(
                status_code=422,
                content=_transport_error("RENDER_FLOOR_NOT_FOUND", str(exc), "/floor_id"),
            )
        except NoRenderableGeometryError as exc:
            return JSONResponse(
                status_code=422,
                content=_transport_error("RENDER_NO_GEOMETRY", str(exc), "/entities"),
            )
        return Response(content=svg, media_type="image/svg+xml")

    @app.post("/v1/models/render/ir")
    def render_ir(
        model: Annotated[dict[str, Any], Body()],
        floor_id: Annotated[str | None, Query()] = None,
    ) -> JSONResponse:
        json_issue = strict_json.issue(model)
        if json_issue is not None:
            report = ValidationReport.create(model, (json_issue,))
            return JSONResponse(status_code=422, content=report.to_dict())
        try:
            render_document = application.render_ir(model, floor_id)
        except ModelValidationError as exc:
            return JSONResponse(status_code=422, content=exc.report.to_dict())
        except FloorNotFoundError as exc:
            return JSONResponse(
                status_code=422,
                content=_transport_error("RENDER_FLOOR_NOT_FOUND", str(exc), "/floor_id"),
            )
        except NoRenderableGeometryError as exc:
            return JSONResponse(
                status_code=422,
                content=_transport_error("RENDER_NO_GEOMETRY", str(exc), "/entities"),
            )
        return JSONResponse(content=render_document.to_dict())

    return app


app = create_app()
