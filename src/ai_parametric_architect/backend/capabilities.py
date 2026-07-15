"""Allowlisted public capability flags for the HTTP adapter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PublicCapabilities:
    """Trusted deployment declarations; never inferred from environment or secrets."""

    openai_requirement_parser_available: bool = False
    benchmark_live_mode_available: bool = False
    live_planning_preview_available: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            (
                "openai_requirement_parser_available",
                self.openai_requirement_parser_available,
            ),
            ("benchmark_live_mode_available", self.benchmark_live_mode_available),
            ("live_planning_preview_available", self.live_planning_preview_available),
        ):
            if type(value) is not bool:
                raise TypeError(f"{name} must be an exact boolean.")

    def to_dict(self) -> dict[str, bool]:
        return {
            "openai_requirement_parser_available": self.openai_requirement_parser_available,
            "benchmark_live_mode_available": self.benchmark_live_mode_available,
            "live_planning_preview_available": self.live_planning_preview_available,
        }


__all__ = ["PublicCapabilities"]
