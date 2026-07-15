from __future__ import annotations

import pytest

from ai_parametric_architect.domain import InvalidPatchError
from ai_parametric_architect.editing import decode_pointer


@pytest.mark.parametrize(
    ("pointer", "tokens"),
    [
        ("", ()),
        ("/", ("",)),
        ("/rooms/0/name", ("rooms", "0", "name")),
        ("/a~1b/~0key", ("a/b", "~key")),
        ("/~01", ("~1",)),
    ],
)
def test_decode_pointer_obeys_rfc6901(pointer: str, tokens: tuple[str, ...]) -> None:
    assert decode_pointer(pointer) == tokens


@pytest.mark.parametrize("pointer", ["rooms/0", "/bad~", "/bad~2", "/bad~01~"])
def test_decode_pointer_rejects_malformed_pointer(pointer: str) -> None:
    with pytest.raises(InvalidPatchError) as error:
        decode_pointer(pointer)

    assert error.value.path == pointer
    reason = error.value.details["reason"]
    assert isinstance(reason, str)
    assert reason.startswith("INVALID_POINTER")
