from __future__ import annotations

from typing import Any, cast

import pytest

from ai_parametric_architect.domain import InvalidDesignIntentError
from ai_parametric_architect.intent import (
    MAX_INTENT_ROOMS,
    DesignIntent,
    RoomRequirement,
    SpatialConstraint,
    SpatialRelation,
)


def constraint(
    relation: SpatialRelation | str = SpatialRelation.ADJACENT_TO,
    *,
    source: str = "kitchen",
    target: str = "dining",
    required: bool = True,
) -> SpatialConstraint:
    return SpatialConstraint(
        source_room_type=source,
        relation=relation,
        target_room_type=target,
        required=required,
    )


def test_room_requirement_is_strict_immutable_and_json_compatible() -> None:
    requirement = RoomRequirement("bedroom", 3)

    assert requirement.to_dict() == {"room_type": "bedroom", "count": 3}
    assert RoomRequirement.from_dict(requirement.to_dict()) == requirement


@pytest.mark.parametrize(
    ("room_type", "count", "expected_path"),
    [
        ("Bedroom", 1, "/room_type"),
        ("bed room", 1, "/room_type"),
        ("bedroom", 0, "/count"),
        ("bedroom", MAX_INTENT_ROOMS + 1, "/count"),
        ("bedroom", True, "/count"),
    ],
)
def test_room_requirement_rejects_noncanonical_values(
    room_type: object,
    count: object,
    expected_path: str,
) -> None:
    with pytest.raises(InvalidDesignIntentError) as error:
        RoomRequirement(cast(Any, room_type), cast(Any, count))

    assert error.value.path == expected_path


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"room_type": "bedroom", "count": 1, "extra": True},
        {"room_type": 1, "count": 1},
        {"room_type": "bedroom", "count": 1.5},
    ],
)
def test_room_requirement_from_dict_rejects_malformed_payload(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(InvalidDesignIntentError):
        RoomRequirement.from_dict(payload)


def test_spatial_constraint_has_stable_strongly_typed_json_shape() -> None:
    value = constraint(required=False)

    assert value.relation is SpatialRelation.ADJACENT_TO
    assert value.to_dict() == {
        "source_room_type": "kitchen",
        "relation": "adjacent_to",
        "target_room_type": "dining",
        "required": False,
    }
    assert SpatialConstraint.from_dict(value.to_dict()) == value


@pytest.mark.parametrize(
    ("arguments", "expected_path"),
    [
        (
            {
                "source_room_type": "Kitchen",
                "relation": "near",
                "target_room_type": "dining",
            },
            "/source_room_type",
        ),
        (
            {
                "source_room_type": "kitchen",
                "relation": "overlaps",
                "target_room_type": "dining",
            },
            "/relation",
        ),
        (
            {
                "source_room_type": "kitchen",
                "relation": "near",
                "target_room_type": "kitchen",
            },
            "/target_room_type",
        ),
        (
            {
                "source_room_type": "kitchen",
                "relation": "near",
                "target_room_type": "dining",
                "required": 1,
            },
            "/required",
        ),
    ],
)
def test_spatial_constraint_rejects_invalid_semantics(
    arguments: dict[str, object],
    expected_path: str,
) -> None:
    with pytest.raises(InvalidDesignIntentError) as error:
        SpatialConstraint(**cast(Any, arguments))

    assert error.value.path == expected_path


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "source_room_type": "kitchen",
            "relation": "near",
            "target_room_type": "dining",
            "required": True,
            "extra": True,
        },
        {
            "source_room_type": 1,
            "relation": "near",
            "target_room_type": "dining",
            "required": True,
        },
        {
            "source_room_type": "kitchen",
            "relation": 1,
            "target_room_type": "dining",
            "required": True,
        },
        {
            "source_room_type": "kitchen",
            "relation": "near",
            "target_room_type": 1,
            "required": True,
        },
        {
            "source_room_type": "kitchen",
            "relation": "near",
            "target_room_type": "dining",
            "required": 1,
        },
    ],
)
def test_spatial_constraint_from_dict_rejects_malformed_payload(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(InvalidDesignIntentError):
        SpatialConstraint.from_dict(payload)


def test_expanded_and_compact_room_inputs_normalize_to_one_intent() -> None:
    constraints = [
        constraint(SpatialRelation.NORTH_OF, source="bedroom", target="living"),
        constraint(source="kitchen", target="living", required=False),
    ]
    expanded = DesignIntent(
        building_type="house",
        area=120,
        rooms=("living", "bedroom", "bedroom", "kitchen"),
        orientation="south",
        spatial_constraints=list(reversed(constraints)),
    )
    compact = DesignIntent(
        building_type="house",
        area=120,
        room_requirements=(
            RoomRequirement("living"),
            RoomRequirement("bedroom", 2),
            RoomRequirement("kitchen"),
        ),
        orientation="south",
        spatial_constraints=constraints,
    )

    assert expanded == compact
    assert expanded.room_requirements == (
        RoomRequirement("living"),
        RoomRequirement("bedroom", 2),
        RoomRequirement("kitchen"),
    )
    assert expanded.spatial_constraints == tuple(
        sorted(
            constraints,
            key=lambda value: (
                value.source_room_type,
                value.relation.value,
                value.target_room_type,
                not value.required,
            ),
        )
    )
    assert DesignIntent.from_dict(expanded.to_dict()) == expanded
    assert DesignIntent.from_dict(expanded.to_compact_dict()) == expanded


def test_design_intent_defensively_copies_compact_inputs() -> None:
    requirements = [RoomRequirement("bedroom", 2)]
    constraints = [constraint(source="bedroom", target="living")]
    requirements.append(RoomRequirement("living"))
    intent = DesignIntent(
        building_type="house",
        area=90,
        room_requirements=requirements,
        spatial_constraints=constraints,
    )
    requirements.append(RoomRequirement("study"))
    constraints.clear()

    assert intent.rooms == ("bedroom", "bedroom", "living")
    assert len(intent.spatial_constraints) == 1


def test_design_intent_requires_exactly_one_room_representation() -> None:
    with pytest.raises(InvalidDesignIntentError):
        DesignIntent(building_type="house", area=90)
    with pytest.raises(InvalidDesignIntentError):
        DesignIntent(
            building_type="house",
            area=90,
            rooms=("bedroom",),
            room_requirements=(RoomRequirement("bedroom"),),
        )


def test_compact_requirements_are_unique_and_total_count_is_bounded() -> None:
    with pytest.raises(InvalidDesignIntentError, match="unique"):
        DesignIntent(
            building_type="house",
            area=90,
            room_requirements=(
                RoomRequirement("bedroom"),
                RoomRequirement("bedroom"),
            ),
        )
    with pytest.raises(InvalidDesignIntentError) as error:
        DesignIntent(
            building_type="house",
            area=90,
            room_requirements=(
                RoomRequirement("bedroom", 33),
                RoomRequirement("bathroom", 32),
            ),
        )

    assert error.value.details == {"maximum": MAX_INTENT_ROOMS}
    assert error.value.path == "/room_requirements"


def test_constraints_must_be_unique_and_reference_requested_room_types() -> None:
    value = constraint()
    with pytest.raises(InvalidDesignIntentError, match="unique"):
        DesignIntent(
            building_type="house",
            area=90,
            rooms=("kitchen", "dining"),
            spatial_constraints=(value, value),
        )
    with pytest.raises(InvalidDesignIntentError) as error:
        DesignIntent(
            building_type="house",
            area=90,
            rooms=("bedroom",),
            spatial_constraints=(value,),
        )

    assert error.value.path == "/spatial_constraints/0"
    assert error.value.details == {"missing_room_types": ["kitchen", "dining"]}


def test_from_dict_reports_nested_constraint_and_requirement_paths() -> None:
    with pytest.raises(InvalidDesignIntentError) as requirement_error:
        DesignIntent.from_dict(
            {
                "building_type": "house",
                "area": 90,
                "room_requirements": [{"room_type": "Bedroom", "count": 1}],
            }
        )
    with pytest.raises(InvalidDesignIntentError) as constraint_error:
        DesignIntent.from_dict(
            {
                "building_type": "house",
                "area": 90,
                "rooms": ["bedroom", "living"],
                "spatial_constraints": [
                    {
                        "source_room_type": "bedroom",
                        "relation": "invalid",
                        "target_room_type": "living",
                        "required": True,
                    }
                ],
            }
        )

    assert requirement_error.value.path == "/room_requirements/0/room_type"
    assert constraint_error.value.path == "/spatial_constraints/0/relation"


@pytest.mark.parametrize(
    "payload",
    [
        {"building_type": "house", "area": 90},
        {
            "building_type": "house",
            "area": 90,
            "rooms": ["bedroom"],
            "room_requirements": [{"room_type": "bedroom", "count": 1}],
        },
        {
            "building_type": "house",
            "area": 90,
            "rooms": ["bedroom"],
            "spatial_constraints": "none",
        },
        {
            "building_type": "house",
            "area": 90,
            "rooms": ["bedroom"],
            "spatial_constraints": ["invalid"],
        },
    ],
)
def test_from_dict_rejects_invalid_representation_shapes(payload: dict[str, Any]) -> None:
    with pytest.raises(InvalidDesignIntentError):
        DesignIntent.from_dict(payload)
