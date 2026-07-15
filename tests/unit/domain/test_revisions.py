from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from ai_parametric_architect.domain import ModelRevision, NonJsonValueError


def make_revision(document: dict[str, Any]) -> ModelRevision:
    return ModelRevision(
        model_id="mdl_house",
        revision_number=1,
        created_at=datetime(2026, 7, 14, 8, 30, tzinfo=UTC),
        parent_revision=0,
        document=document,
    )


def test_revision_is_immutable_envelope_with_defensive_document_copy() -> None:
    source: dict[str, Any] = {
        "schema_version": "1.0.0",
        "model_id": "mdl_house",
        "revision": 1,
        "metadata": {"name": "Original"},
    }
    revision = make_revision(source)

    source["metadata"]["name"] = "Changed outside"
    returned = revision.document
    returned["metadata"]["name"] = "Changed returned copy"

    assert revision.document["metadata"] == {"name": "Original"}
    assert revision.to_dict() == {
        "model_id": "mdl_house",
        "revision_number": 1,
        "created_at": "2026-07-14T08:30:00+00:00",
        "parent_revision": 0,
        "document": {
            "schema_version": "1.0.0",
            "model_id": "mdl_house",
            "revision": 1,
            "metadata": {"name": "Original"},
        },
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"model_id": ""}, "model_id"),
        ({"revision_number": -1}, "revision_number"),
        ({"revision_number": True}, "revision_number"),
        ({"created_at": datetime(2026, 1, 1)}, "timezone-aware"),
        ({"parent_revision": 1}, "parent_revision"),
        ({"parent_revision": -1}, "parent_revision"),
    ],
)
def test_revision_rejects_invalid_envelope_fields(
    overrides: dict[str, object], message: str
) -> None:
    arguments: dict[str, Any] = {
        "model_id": "mdl_house",
        "revision_number": 1,
        "created_at": datetime(2026, 7, 14, tzinfo=UTC),
        "parent_revision": 0,
        "document": {"model_id": "mdl_house", "revision": 1},
    }
    arguments.update(overrides)

    with pytest.raises(ValueError, match=message):
        ModelRevision(**arguments)


@pytest.mark.parametrize(
    "document",
    [
        {"model_id": "mdl_other", "revision": 1},
        {"model_id": "mdl_house", "revision": 2},
        {"model_id": "mdl_house", "revision": True},
    ],
)
def test_revision_must_match_authoritative_document(document: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        make_revision(cast(dict[str, Any], document))


def test_revision_rejects_non_json_snapshot() -> None:
    with pytest.raises(NonJsonValueError):
        make_revision(
            {
                "model_id": "mdl_house",
                "revision": 1,
                "metadata": {"created_at": datetime(2026, 7, 14, tzinfo=UTC)},
            }
        )
