"""Load the versioned, provider-neutral design-intent contract."""

from __future__ import annotations

import json
from importlib.resources import files
from types import MappingProxyType
from typing import Any, Final, cast

from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator


class UnsupportedIntentSchemaVersionError(ValueError):
    """Raised when a caller requests an unknown intent contract version."""


DEFAULT_INTENT_SCHEMA_VERSION: Final = "1.0.0"
SUPPORTED_INTENT_SCHEMA_VERSIONS: Final[tuple[str, ...]] = (DEFAULT_INTENT_SCHEMA_VERSION,)
_SCHEMA_RESOURCES: Final = MappingProxyType(
    {DEFAULT_INTENT_SCHEMA_VERSION: "design-intent-1.0.0.schema.json"}
)


def load_intent_schema(version: str = DEFAULT_INTENT_SCHEMA_VERSION) -> dict[str, Any]:
    """Return a fresh copy of the authoritative schema for ``version``."""

    try:
        resource_name = _SCHEMA_RESOURCES[version]
    except KeyError as error:
        supported = ", ".join(SUPPORTED_INTENT_SCHEMA_VERSIONS)
        raise UnsupportedIntentSchemaVersionError(
            f"Unsupported intent schema version {version!r}; supported versions: {supported}"
        ) from error

    resource = files("ai_parametric_architect.intent.schemas").joinpath(resource_name)
    document = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError(f"Intent schema resource {resource_name!r} must contain an object.")
    return cast(dict[str, Any], document)


def create_intent_schema_validator(
    version: str = DEFAULT_INTENT_SCHEMA_VERSION,
) -> Validator:
    """Create a checked Draft 2020-12 validator for an intent schema version."""

    schema = load_intent_schema(version)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)
