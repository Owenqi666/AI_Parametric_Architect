"""JSON Patch application port."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ai_parametric_architect.domain import PatchOperation


class PatchEngine(Protocol):
    def apply(self, document: object, operations: Sequence[PatchOperation]) -> object: ...
