"""Infrastructure-neutral domain vocabulary."""

from ai_parametric_architect.domain.audit import (
    AuditAction,
    AuditActorType,
    AuditEntry,
    TrustedAuditIdentity,
)
from ai_parametric_architect.domain.design_intent import (
    MAX_INTENT_ROOMS,
    MAX_SPATIAL_CONSTRAINTS,
    DesignIntent,
    RoomRequirement,
    SpatialConstraint,
    SpatialRelation,
)
from ai_parametric_architect.domain.editing_errors import (
    AffectedEntitiesMismatchError,
    EditingError,
    InvalidPatchError,
    ModelAlreadyExistsError,
    ModelNotFoundError,
    NonJsonValueError,
    PatchModelMismatchError,
    ProtectedPathError,
    RedoUnavailableError,
    RevisionConflictError,
    RevisionNotFoundError,
    UndoUnavailableError,
)
from ai_parametric_architect.domain.geometry import (
    PolygonProjection,
    RoomAnalysis,
    SegmentAnalysis,
    SegmentProjection,
)
from ai_parametric_architect.domain.guardrails import (
    DEFAULT_MAX_COORDINATE_MAGNITUDE,
    DEFAULT_MAX_PATCH_OPERATIONS,
    DEFAULT_MAX_POLYGON_VERTICES,
    DEFAULT_MAX_ROOM_AREA,
    DEFAULT_MAX_TOTAL_ENTITIES,
    DEFAULT_MAX_WALL_LENGTH,
    ModelComplexityError,
    ModelComplexityPolicy,
    StrictJsonTreeGuard,
)
from ai_parametric_architect.domain.issues import Severity, ValidationIssue, ValidationReport
from ai_parametric_architect.domain.json_pointers import (
    JsonPointerSyntaxError,
    decode_json_pointer,
)
from ai_parametric_architect.domain.json_values import MAX_JSON_DEPTH, ensure_json_value
from ai_parametric_architect.domain.model import Entity, ModelDocument, Point2, Ring2
from ai_parametric_architect.domain.patch_impacts import derive_affected_entity_ids
from ai_parametric_architect.domain.patches import (
    PatchOperation,
    PatchOperationType,
    PatchProposal,
)
from ai_parametric_architect.domain.planning_errors import (
    InvalidDesignIntentError,
    PlannerContractError,
    PlanningCapacityError,
    PlanningContextError,
    PlanningError,
    PlanningPolicyError,
    PlanningSolverError,
    RequirementParseError,
)
from ai_parametric_architect.domain.planning_record import (
    PLANNING_EXTENSION_KEY,
    PLANNING_REALIZATION_SCOPE,
    PLANNING_RECORD_VERSION,
    PlanningRecord,
    RoomAssignment,
)
from ai_parametric_architect.domain.precision import GeometryPrecisionPolicy
from ai_parametric_architect.domain.restorations import RestorationPreview
from ai_parametric_architect.domain.revisions import ModelRevision

__all__ = [
    "DEFAULT_MAX_COORDINATE_MAGNITUDE",
    "DEFAULT_MAX_PATCH_OPERATIONS",
    "DEFAULT_MAX_POLYGON_VERTICES",
    "DEFAULT_MAX_ROOM_AREA",
    "DEFAULT_MAX_TOTAL_ENTITIES",
    "DEFAULT_MAX_WALL_LENGTH",
    "MAX_INTENT_ROOMS",
    "MAX_JSON_DEPTH",
    "MAX_SPATIAL_CONSTRAINTS",
    "PLANNING_EXTENSION_KEY",
    "PLANNING_REALIZATION_SCOPE",
    "PLANNING_RECORD_VERSION",
    "AffectedEntitiesMismatchError",
    "AuditAction",
    "AuditActorType",
    "AuditEntry",
    "DesignIntent",
    "EditingError",
    "Entity",
    "GeometryPrecisionPolicy",
    "InvalidDesignIntentError",
    "InvalidPatchError",
    "JsonPointerSyntaxError",
    "ModelAlreadyExistsError",
    "ModelComplexityError",
    "ModelComplexityPolicy",
    "ModelDocument",
    "ModelNotFoundError",
    "ModelRevision",
    "NonJsonValueError",
    "PatchModelMismatchError",
    "PatchOperation",
    "PatchOperationType",
    "PatchProposal",
    "PlannerContractError",
    "PlanningCapacityError",
    "PlanningContextError",
    "PlanningError",
    "PlanningPolicyError",
    "PlanningRecord",
    "PlanningSolverError",
    "Point2",
    "PolygonProjection",
    "ProtectedPathError",
    "RedoUnavailableError",
    "RequirementParseError",
    "RestorationPreview",
    "RevisionConflictError",
    "RevisionNotFoundError",
    "Ring2",
    "RoomAnalysis",
    "RoomAssignment",
    "RoomRequirement",
    "SegmentAnalysis",
    "SegmentProjection",
    "Severity",
    "SpatialConstraint",
    "SpatialRelation",
    "StrictJsonTreeGuard",
    "TrustedAuditIdentity",
    "UndoUnavailableError",
    "ValidationIssue",
    "ValidationReport",
    "decode_json_pointer",
    "derive_affected_entity_ids",
    "ensure_json_value",
]
