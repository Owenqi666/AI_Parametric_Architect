from __future__ import annotations

from typing import Any, cast

import pytest

from ai_parametric_architect.domain import (
    MAX_INTENT_ROOMS,
    DesignIntent,
    InvalidDesignIntentError,
    ensure_json_value,
)


def test_design_intent_round_trips_requested_shape_and_copies_rooms() -> None:
    rooms = ["living", "bedroom"]
    intent = DesignIntent(
        building_type="house",
        area=120,
        rooms=rooms,
        orientation="south",
    )
    rooms.append("kitchen")

    assert intent.rooms == ("living", "bedroom")
    assert intent.to_dict() == {
        "building_type": "house",
        "area": 120,
        "rooms": ["living", "bedroom"],
        "orientation": "south",
    }
    assert DesignIntent.from_dict(intent.to_dict()) == intent
    ensure_json_value(intent.to_dict())


def test_fractional_area_is_not_rounded() -> None:
    intent = DesignIntent(
        building_type="apartment",
        area=88.5,
        rooms=("bedroom",),
    )

    assert intent.to_dict()["area"] == 88.5
    assert intent.orientation is None


@pytest.mark.parametrize("area", [0, -1, True, float("nan"), float("inf"), 10**400])
def test_design_intent_requires_positive_finite_area(area: object) -> None:
    with pytest.raises(InvalidDesignIntentError) as error:
        DesignIntent(
            building_type="house",
            area=cast(Any, area),
            rooms=("bedroom",),
        )

    assert error.value.path == "/area"


@pytest.mark.parametrize("building_type", ["", " House", "HOUSE", "two words", 1])
def test_building_type_must_be_canonical_token(building_type: object) -> None:
    with pytest.raises(InvalidDesignIntentError) as error:
        DesignIntent(
            building_type=cast(Any, building_type),
            area=120,
            rooms=("bedroom",),
        )

    assert error.value.path == "/building_type"


@pytest.mark.parametrize(
    "rooms",
    [
        (),
        "bedroom",
        ("Bedroom",),
        ("two words",),
        cast(Any, (1,)),
    ],
)
def test_rooms_must_be_nonempty_canonical_array(rooms: object) -> None:
    with pytest.raises(InvalidDesignIntentError):
        DesignIntent(
            building_type="house",
            area=120,
            rooms=cast(Any, rooms),
        )


def test_room_count_is_bounded() -> None:
    with pytest.raises(InvalidDesignIntentError) as error:
        DesignIntent(
            building_type="house",
            area=120,
            rooms=("bedroom",) * (MAX_INTENT_ROOMS + 1),
        )

    assert error.value.details == {"maximum": MAX_INTENT_ROOMS}


@pytest.mark.parametrize("orientation", ["northeast", "South", "", 1])
def test_orientation_is_optional_cardinal_token(orientation: object) -> None:
    with pytest.raises(InvalidDesignIntentError):
        DesignIntent(
            building_type="house",
            area=120,
            rooms=("bedroom",),
            orientation=cast(Any, orientation),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"building_type": "house", "area": 120, "rooms": ["bedroom"], "extra": 1},
        {"building_type": 1, "area": 120, "rooms": ["bedroom"]},
        {"building_type": "house", "area": "120", "rooms": ["bedroom"]},
        {"building_type": "house", "area": 120, "rooms": "bedroom"},
        {
            "building_type": "house",
            "area": 120,
            "rooms": ["bedroom"],
            "orientation": 1,
        },
    ],
)
def test_from_dict_rejects_malformed_payload(payload: dict[str, Any]) -> None:
    with pytest.raises(InvalidDesignIntentError):
        DesignIntent.from_dict(payload)
