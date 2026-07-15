from __future__ import annotations

from typing import Any, cast

import pytest

from ai_parametric_architect.domain import JsonPointerSyntaxError, decode_json_pointer


@pytest.mark.parametrize(
    ("pointer", "tokens"),
    [
        ("", ()),
        ("/", ("",)),
        ("/entities/rooms/rom_a", ("entities", "rooms", "rom_a")),
        ("/a~1b/~0key", ("a/b", "~key")),
        ("/~01", ("~1",)),
    ],
)
def test_neutral_json_pointer_decoder_obeys_rfc6901(
    pointer: str,
    tokens: tuple[str, ...],
) -> None:
    assert decode_json_pointer(pointer) == tokens


@pytest.mark.parametrize(
    ("pointer", "reason"),
    [
        (cast(Any, 1), "INVALID_POINTER_TYPE"),
        ("entities/rooms", "INVALID_POINTER_PREFIX"),
        ("/bad~", "INVALID_POINTER_ESCAPE"),
        ("/bad~2", "INVALID_POINTER_ESCAPE"),
    ],
)
def test_neutral_json_pointer_decoder_reports_stable_syntax_reason(
    pointer: str,
    reason: str,
) -> None:
    with pytest.raises(JsonPointerSyntaxError) as captured:
        decode_json_pointer(pointer)

    assert captured.value.reason == reason
