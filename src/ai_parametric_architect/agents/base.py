"""Provider-neutral contracts shared by all architecture agents."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)


@runtime_checkable
class Agent(Protocol[InputT, OutputT]):
    """A deterministic boundary from one typed value to another."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def run(self, value: InputT) -> OutputT: ...
