from __future__ import annotations

from typing import Any, cast

import pytest

from ai_parametric_architect.domain import AuditAction, NonJsonValueError, RestorationPreview


def make_preview(**overrides: Any) -> RestorationPreview:
    arguments: dict[str, Any] = {
        "model_id": "mdl_house",
        "action": AuditAction.UNDO,
        "head_revision": 2,
        "target_revision": 1,
        "document": {"model_id": "mdl_house", "revision": 1, "name": "First"},
    }
    arguments.update(overrides)
    return RestorationPreview(**arguments)


def test_restoration_preview_is_immutable_defensive_token() -> None:
    source: dict[str, Any] = {
        "model_id": "mdl_house",
        "revision": 1,
        "metadata": {"name": "First"},
    }
    preview = make_preview(document=source)

    source["metadata"]["name"] = "External"
    returned = preview.document
    returned["metadata"]["name"] = "Returned"

    assert preview.to_dict() == {
        "model_id": "mdl_house",
        "action": "undo",
        "head_revision": 2,
        "target_revision": 1,
        "document": {
            "model_id": "mdl_house",
            "revision": 1,
            "metadata": {"name": "First"},
        },
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"model_id": ""},
        {"action": AuditAction.INITIALIZE},
        {"action": cast(Any, "undo")},
        {"head_revision": True},
        {"head_revision": -1},
        {"target_revision": 1.0},
        {"target_revision": -1},
        {"target_revision": 2},
        {"target_revision": 3},
        {"document": {"model_id": "other", "revision": 1}},
        {"document": {"model_id": "mdl_house", "revision": 0}},
        {"document": {"model_id": "mdl_house", "revision": True}},
    ],
)
def test_restoration_preview_rejects_invalid_token(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        make_preview(**overrides)


def test_restoration_preview_requires_json_document() -> None:
    shared: list[object] = []

    with pytest.raises(NonJsonValueError):
        make_preview(
            document={
                "model_id": "mdl_house",
                "revision": 1,
                "first": shared,
                "second": shared,
            }
        )
