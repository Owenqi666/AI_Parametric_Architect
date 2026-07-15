"""Small deterministic grammar for supported Chinese and English requirements."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from math import isfinite

from ai_parametric_architect.domain import (
    MAX_INTENT_ROOMS,
    DesignIntent,
    InvalidDesignIntentError,
    RequirementParseError,
)

_ENGLISH_COUNTS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_ENGLISH_NUMBER_TOKEN = rf"\b(?:{'|'.join(_ENGLISH_COUNTS)})\b"
_CHINESE_NUMBER_TOKEN = r"[零〇一二两三四五六七八九十]+"
_NUMBER_TOKEN = rf"(?:\d+|{_CHINESE_NUMBER_TOKEN}|{_ENGLISH_NUMBER_TOKEN})"
_AREA_PATTERN = re.compile(
    r"(?<![\d.])(?P<area>\d+(?:\.\d+)?)\s*"
    r"(?:平方米|平米|m2|m\^2|sqm|sq\.?\s*m|square\s*(?:meters?|metres?))",
    re.IGNORECASE,
)
_CHINESE_AREA_PATTERN = re.compile(
    r"(?P<area>[零〇一二两三四五六七八九十百千万]+)\s*(?:平方米|平米|m2)",
)
_NEGATIVE_AREA_PATTERN = re.compile(
    r"-\s*\d+(?:\.\d+)?\s*"
    r"(?:平方米|平米|m2|m\^2|sqm|sq\.?\s*m|square\s*(?:meters?|metres?))",
    re.IGNORECASE,
)
_GENERIC_RESIDENTIAL_ROOMS = re.compile(rf"(?P<count>{_NUMBER_TOKEN})\s*(?:室|居)")
_ROOM_NOUN = (
    r"(?:客厅|起居室|餐厅|厨房|卧室|睡房|卫生间|浴室|洗手间|书房|室|居|"
    r"living\s+rooms?|dining\s+rooms?|kitchens?|bedrooms?|bathrooms?|stud(?:y|ies))"
)
_NEGATIVE_ROOM_COUNT = re.compile(
    rf"-\s*{_NUMBER_TOKEN}\s*(?:间|个)?\s*-?\s*{_ROOM_NOUN}",
    re.IGNORECASE,
)
_CHINESE_ROOM_COUNT = re.compile(
    rf"(?P<count>[零〇一二两三四五六七八九十百千万]+)\s*(?:间|个)?\s*{_ROOM_NOUN}",
    re.IGNORECASE,
)

_BUILDING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("apartment", re.compile(r"公寓|\bapartment\b", re.IGNORECASE)),
    ("house", re.compile(r"住宅|住房|\bhouse\b|\bhome\b", re.IGNORECASE)),
    ("office", re.compile(r"办公楼|办公室|办公空间|\boffice\b", re.IGNORECASE)),
    ("villa", re.compile(r"别墅|\bvilla\b", re.IGNORECASE)),
)
_ORIENTATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("east", re.compile(r"朝东|东向|向东|\beast(?:-facing)?\b", re.IGNORECASE)),
    ("north", re.compile(r"朝北|北向|向北|\bnorth(?:-facing)?\b", re.IGNORECASE)),
    ("south", re.compile(r"朝南|南向|向南|\bsouth(?:-facing)?\b", re.IGNORECASE)),
    ("west", re.compile(r"朝西|西向|向西|\bwest(?:-facing)?\b", re.IGNORECASE)),
)
_COMPOUND_ORIENTATION = re.compile(
    r"东南|西南|东北|西北|\b(?:north|south)[ -]?(?:east|west)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_AREA_QUALIFIER = re.compile(
    r"大约|约|至少|最少|不超过|至多|最多|"
    r"\baround\b|\bapproximately\b|\bat least\b|\bup to\b",
    re.IGNORECASE,
)
_UNSUPPORTED_AREA_BASIS = re.compile(
    r"建筑面积|套内面积|使用面积|占地面积|地块|"
    r"\bgross area\b|\bnet area\b|\bsite area\b",
    re.IGNORECASE,
)

_ROOM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "living",
        re.compile(
            rf"(?:(?P<count>{_NUMBER_TOKEN})\s*(?:间|个)?(?:\s*-\s*)?)?\s*"
            r"(?:客厅|起居室|(?<![客餐])(?<!客 )(?<!餐 )厅|\bliving rooms?\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "dining",
        re.compile(
            rf"(?:(?P<count>{_NUMBER_TOKEN})\s*(?:间|个)?(?:\s*-\s*)?)?\s*"
            r"(?:餐厅|\bdining rooms?\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "kitchen",
        re.compile(
            rf"(?:(?P<count>{_NUMBER_TOKEN})\s*(?:间|个)?(?:\s*-\s*)?)?\s*"
            r"(?:厨房|\bkitchens?\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "bedroom",
        re.compile(
            rf"(?:(?P<count>{_NUMBER_TOKEN})\s*(?:间|个)?(?:\s*-\s*)?)?\s*"
            r"(?:卧室|睡房|\bbedrooms?\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "bathroom",
        re.compile(
            rf"(?:(?P<count>{_NUMBER_TOKEN})\s*(?:间|个)?(?:\s*-\s*)?)?\s*"
            r"(?:卫生间|浴室|洗手间|\bbathrooms?\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "study",
        re.compile(
            rf"(?:(?P<count>{_NUMBER_TOKEN})\s*(?:间|个)?(?:\s*-\s*)?)?\s*"
            r"(?:书房|\bstud(?:y|ies)\b)",
            re.IGNORECASE,
        ),
    ),
)
_ROOM_ORDER = tuple(room_type for room_type, _pattern in _ROOM_PATTERNS)


class RuleBasedRequirementParser:
    """Parse only the grammar this milestone can explain deterministically."""

    def parse(self, requirement: str) -> DesignIntent:
        if not isinstance(requirement, str) or not requirement.strip():
            raise RequirementParseError(
                "Requirement text cannot be empty.",
                details={"reason": "EMPTY_REQUIREMENT"},
            )
        normalized = _normalize(requirement)
        building_type = _single_match(
            normalized,
            _BUILDING_PATTERNS,
            field="building_type",
        )
        area = _parse_area(normalized)
        rooms = _parse_rooms(normalized, building_type)
        orientation = _parse_orientation(normalized)
        try:
            return DesignIntent(
                building_type=building_type,
                area=area,
                rooms=rooms,
                orientation=orientation,
            )
        except InvalidDesignIntentError as error:
            raise RequirementParseError(
                f"Parsed requirement produced an invalid design intent: {error}",
                path=error.path,
                details={
                    "reason": "INVALID_DESIGN_INTENT",
                    "cause": error.code,
                    "cause_details": error.details,
                },
            ) from error


def _normalize(requirement: str) -> str:
    normalized = unicodedata.normalize("NFKC", requirement).lower()
    return re.sub(r"\s+", " ", normalized).strip()


def _single_match(
    requirement: str,
    patterns: Iterable[tuple[str, re.Pattern[str]]],
    *,
    field: str,
) -> str:
    matches = [value for value, pattern in patterns if pattern.search(requirement)]
    if not matches:
        raise RequirementParseError(
            f"Requirement does not contain a supported {field}.",
            path=f"/{field}",
            details={"reason": "MISSING_REQUIRED_FIELD", "field": field},
        )
    if len(matches) > 1:
        raise RequirementParseError(
            f"Requirement contains conflicting {field} values.",
            path=f"/{field}",
            details={"reason": "AMBIGUOUS_FIELD", "field": field, "matches": matches},
        )
    return matches[0]


def _parse_area(requirement: str) -> float:
    if _UNSUPPORTED_AREA_QUALIFIER.search(requirement):
        raise RequirementParseError(
            "Approximate or bounded area requirements are not supported yet.",
            path="/area",
            details={"reason": "UNSUPPORTED_AREA_RELATION"},
        )
    if _UNSUPPORTED_AREA_BASIS.search(requirement):
        raise RequirementParseError(
            "Explicit area bases are not supported by DesignIntent v1.",
            path="/area",
            details={"reason": "UNSUPPORTED_AREA_BASIS"},
        )
    if _NEGATIVE_AREA_PATTERN.search(requirement):
        raise RequirementParseError(
            "Area must be positive.",
            path="/area",
            details={"reason": "INVALID_AREA"},
        )
    if _CHINESE_AREA_PATTERN.search(requirement):
        raise RequirementParseError(
            "Chinese-numeral areas are not supported yet.",
            path="/area",
            details={"reason": "UNSUPPORTED_AREA_NUMBER"},
        )
    matches = [float(match.group("area")) for match in _AREA_PATTERN.finditer(requirement)]
    if not matches:
        raise RequirementParseError(
            "Requirement does not contain an area in square metres.",
            path="/area",
            details={"reason": "MISSING_REQUIRED_FIELD", "field": "area"},
        )
    if any(not isfinite(value) or value <= 0 for value in matches):
        raise RequirementParseError(
            "Area must be a positive finite number.",
            path="/area",
            details={"reason": "INVALID_AREA"},
        )
    if len(set(matches)) > 1:
        raise RequirementParseError(
            "Requirement contains conflicting area values.",
            path="/area",
            details={"reason": "AMBIGUOUS_FIELD", "field": "area", "matches": matches},
        )
    return matches[0]


def _parse_rooms(requirement: str, building_type: str) -> tuple[str, ...]:
    if _NEGATIVE_ROOM_COUNT.search(requirement):
        raise RequirementParseError(
            "Room counts must be positive.",
            path="/rooms",
            details={"reason": "INVALID_ROOM_COUNT"},
        )
    for match in _CHINESE_ROOM_COUNT.finditer(requirement):
        _parse_count(match.group("count"))

    generic_counts = [
        _parse_count(match.group("count"))
        for match in _GENERIC_RESIDENTIAL_ROOMS.finditer(requirement)
    ]
    if len(set(generic_counts)) > 1:
        raise RequirementParseError(
            "Requirement contains conflicting residential room counts.",
            path="/rooms",
            details={"reason": "AMBIGUOUS_FIELD", "field": "rooms"},
        )
    if generic_counts and building_type not in {"apartment", "house", "villa"}:
        raise RequirementParseError(
            "The Chinese '室/居' rule is only defined for residential buildings.",
            path="/rooms",
            details={"reason": "AMBIGUOUS_ROOM_SEMANTICS"},
        )

    counts: Counter[str] = Counter()
    explicit_bedroom = False
    for room_type, pattern in _ROOM_PATTERNS:
        matches = list(pattern.finditer(requirement))
        if room_type == "bedroom" and matches:
            explicit_bedroom = True
        parsed_counts = [
            (
                1
                if (count_token := match.groupdict().get("count")) is None
                else _parse_count(count_token)
            )
            for match in matches
        ]
        if len(parsed_counts) > 1:
            raise RequirementParseError(
                f"Requirement contains repeated {room_type} declarations.",
                path="/rooms",
                details={
                    "reason": "AMBIGUOUS_FIELD",
                    "field": "rooms",
                    "room_type": room_type,
                    "matches": parsed_counts,
                },
            )
        if parsed_counts:
            counts[room_type] = parsed_counts[0]
    if generic_counts and explicit_bedroom:
        raise RequirementParseError(
            "Generic and explicit bedroom counts cannot be combined unambiguously.",
            path="/rooms",
            details={"reason": "AMBIGUOUS_FIELD", "field": "rooms"},
        )
    if generic_counts:
        counts["bedroom"] += generic_counts[0]
    if not counts:
        raise RequirementParseError(
            "Requirement does not contain a supported room request.",
            path="/rooms",
            details={"reason": "MISSING_REQUIRED_FIELD", "field": "rooms"},
        )
    return tuple(room_type for room_type in _ROOM_ORDER for _ in range(counts[room_type]))


def _parse_orientation(requirement: str) -> str | None:
    if _COMPOUND_ORIENTATION.search(requirement):
        raise RequirementParseError(
            "Diagonal orientations are not supported by DesignIntent v1.",
            path="/orientation",
            details={"reason": "UNSUPPORTED_ORIENTATION"},
        )
    matches = [
        orientation for orientation, pattern in _ORIENTATION_PATTERNS if pattern.search(requirement)
    ]
    if len(matches) > 1:
        raise RequirementParseError(
            "Requirement contains conflicting orientations.",
            path="/orientation",
            details={"reason": "AMBIGUOUS_FIELD", "field": "orientation"},
        )
    return matches[0] if matches else None


def _parse_count(value: str) -> int:
    if value.isascii() and value.isdigit():
        count = int(value)
    elif value in _ENGLISH_COUNTS:
        count = _ENGLISH_COUNTS[value]
    else:
        digits = {
            "零": 0,
            "\N{IDEOGRAPHIC NUMBER ZERO}": 0,
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }
        if value == "十":
            count = 10
        elif "十" in value and value.count("十") == 1:
            tens, ones = value.split("十", maxsplit=1)
            if (tens and tens not in digits) or (ones and ones not in digits):
                count = -1
            else:
                count = (digits.get(tens, 1) * 10) + (digits.get(ones, 0) if ones else 0)
        else:
            count = digits.get(value, -1)
    if count < 0:
        raise RequirementParseError(
            "Room count is not supported.",
            path="/rooms",
            details={"reason": "UNSUPPORTED_ROOM_COUNT", "value": value},
        )
    if count == 0 or count > MAX_INTENT_ROOMS:
        raise RequirementParseError(
            f"Room count must be between 1 and {MAX_INTENT_ROOMS}.",
            path="/rooms",
            details={
                "reason": "INVALID_ROOM_COUNT",
                "value": value,
                "maximum": MAX_INTENT_ROOMS,
            },
        )
    return count
