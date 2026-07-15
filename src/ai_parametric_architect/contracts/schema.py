"""Access to versioned model schemas.

The JSON files in :mod:`ai_parametric_architect.contracts.schemas` are the
authoritative structural contract. This module deliberately does not recreate the
model as a second set of Python classes.
"""

from __future__ import annotations

import json
from importlib.resources import files
from types import MappingProxyType
from typing import Any, Final, cast

from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator


class UnsupportedSchemaVersionError(ValueError):
    """Raised when a model requests an unknown contract version."""


SUPPORTED_SCHEMA_VERSIONS: Final[tuple[str, ...]] = ("1.0.0",)
_SCHEMA_RESOURCES: Final = MappingProxyType({"1.0.0": "model-1.0.0.schema.json"})


def load_model_schema(version: str) -> dict[str, Any]:
    """Load a fresh copy of the authoritative schema for ``version``."""

    try:
        resource_name = _SCHEMA_RESOURCES[version]
    except KeyError as exc:
        supported = ", ".join(SUPPORTED_SCHEMA_VERSIONS)
        raise UnsupportedSchemaVersionError(
            f"Unsupported schema version {version!r}; supported versions: {supported}"
        ) from exc

    resource = files("ai_parametric_architect.contracts.schemas").joinpath(resource_name)
    document = json.loads(resource.read_text(encoding="utf-8"))
    return cast(dict[str, Any], document)


def create_model_validator(version: str) -> Validator:
    """Create a Draft 2020-12 validator for a model schema version."""

    schema = load_model_schema(version)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)
