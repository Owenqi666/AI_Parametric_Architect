"""Versioned, provider-neutral design-intent contract."""

from ai_parametric_architect.intent.models import (
    MAX_INTENT_ROOMS,
    MAX_SPATIAL_CONSTRAINTS,
    DesignIntent,
    RoomRequirement,
    SpatialConstraint,
    SpatialRelation,
)
from ai_parametric_architect.intent.schema import (
    DEFAULT_INTENT_SCHEMA_VERSION,
    SUPPORTED_INTENT_SCHEMA_VERSIONS,
    UnsupportedIntentSchemaVersionError,
    create_intent_schema_validator,
    load_intent_schema,
)
from ai_parametric_architect.intent.validator import IntentValidator

__all__ = [
    "DEFAULT_INTENT_SCHEMA_VERSION",
    "MAX_INTENT_ROOMS",
    "MAX_SPATIAL_CONSTRAINTS",
    "SUPPORTED_INTENT_SCHEMA_VERSIONS",
    "DesignIntent",
    "IntentValidator",
    "RoomRequirement",
    "SpatialConstraint",
    "SpatialRelation",
    "UnsupportedIntentSchemaVersionError",
    "create_intent_schema_validator",
    "load_intent_schema",
]
