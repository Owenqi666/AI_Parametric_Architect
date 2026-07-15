from __future__ import annotations

import math

import pytest

from ai_parametric_architect.domain import (
    NonJsonValueError,
    Severity,
    ValidationIssue,
    ValidationReport,
)


def test_validation_report_serializes_stable_shape() -> None:
    issue = ValidationIssue(
        code="GEOMETRY.ROOM.INVALID",
        severity=Severity.ERROR,
        message="Room polygon is invalid.",
        path="/entities/rooms/rom_living/geometry",
        entity_ids=("rom_living",),
        details={"reason": "Self-intersection"},
    )

    report = ValidationReport.create(
        {"model_id": "mdl_house", "revision": 3},
        [issue],
    )

    assert not report.valid
    assert report.error_count == 1
    assert report.to_dict() == {
        "valid": False,
        "model_id": "mdl_house",
        "revision": 3,
        "error_count": 1,
        "issues": [
            {
                "code": "GEOMETRY.ROOM.INVALID",
                "severity": "error",
                "message": "Room polygon is invalid.",
                "path": "/entities/rooms/rom_living/geometry",
                "entity_ids": ["rom_living"],
                "details": {"reason": "Self-intersection"},
            }
        ],
    }


def test_warning_does_not_invalidate_report() -> None:
    warning = ValidationIssue(
        code="RULE.WARNING",
        severity=Severity.WARNING,
        message="Advisory only.",
        path="/",
    )

    assert ValidationReport.create({}, [warning]).valid


@pytest.mark.parametrize("invalid", [math.inf, math.nan, ("not", "json")])
def test_issue_details_reject_non_json_values(invalid: object) -> None:
    with pytest.raises(NonJsonValueError):
        ValidationIssue(
            code="RULE.INVALID_DETAILS",
            severity=Severity.ERROR,
            message="Invalid diagnostic details.",
            path="/",
            details={"value": invalid},
        )


def test_issue_details_must_be_a_json_object() -> None:
    with pytest.raises(NonJsonValueError, match="JSON object"):
        ValidationIssue(
            code="RULE.INVALID_DETAILS",
            severity=Severity.ERROR,
            message="Invalid diagnostic details.",
            path="/",
            details=[],  # type: ignore[arg-type]
        )


def test_issue_details_are_defensively_copied() -> None:
    source = {"values": [1]}
    issue = ValidationIssue(
        code="RULE.STABLE_DETAILS",
        severity=Severity.ERROR,
        message="Stable diagnostic details.",
        path="/",
        details=source,
    )

    source["values"].append(2)
    serialized = issue.to_dict()
    serialized_details = serialized["details"]
    assert isinstance(serialized_details, dict)
    serialized_details["values"] = [3]

    assert issue.to_dict()["details"] == {"values": [1]}
