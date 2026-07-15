"""Stable CP-SAT decision-variable construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ortools.sat.python import cp_model

from ai_parametric_architect.planning.solver.models import PlanningProblem, RoomSpecification

ORIENTATION_ORDER: Final = ("north", "east", "south", "west", "interior")


@dataclass(frozen=True, slots=True)
class RoomDecisionVariables:
    specification: RoomSpecification
    x: cp_model.IntVar
    y: cp_model.IntVar
    width: cp_model.IntVar
    height: cp_model.IntVar
    end_x: cp_model.IntVar
    end_y: cp_model.IntVar
    area: cp_model.IntVar
    center_x2: cp_model.IntVar
    center_y2: cp_model.IntVar
    target_area_deviation: cp_model.IntVar
    x_interval: cp_model.IntervalVar
    y_interval: cp_model.IntervalVar
    orientation_literals: tuple[cp_model.IntVar, ...]

    def orientation_literal(self, orientation: str) -> cp_model.IntVar:
        return self.orientation_literals[ORIENTATION_ORDER.index(orientation)]


def create_room_variables(
    model: cp_model.CpModel, problem: PlanningProblem
) -> tuple[RoomDecisionVariables, ...]:
    result: list[RoomDecisionVariables] = []
    boundary = problem.boundary
    for room in problem.rooms:
        prefix = room.plan_id
        x = model.new_int_var(0, boundary.width - room.minimum_width_units, f"{prefix}_x")
        y = model.new_int_var(0, boundary.height - room.minimum_height_units, f"{prefix}_y")
        width = model.new_int_var(room.minimum_width_units, boundary.width, f"{prefix}_width")
        height = model.new_int_var(room.minimum_height_units, boundary.height, f"{prefix}_height")
        end_x = model.new_int_var(room.minimum_width_units, boundary.width, f"{prefix}_end_x")
        end_y = model.new_int_var(room.minimum_height_units, boundary.height, f"{prefix}_end_y")
        area = model.new_int_var(
            room.minimum_area_units,
            problem.maximum_room_area_units,
            f"{prefix}_area",
        )
        center_x2 = model.new_int_var(0, boundary.width * 2, f"{prefix}_center_x2")
        center_y2 = model.new_int_var(0, boundary.height * 2, f"{prefix}_center_y2")
        deviation = model.new_int_var(
            0, problem.maximum_room_area_units, f"{prefix}_target_area_deviation"
        )
        model.add(end_x == x + width)
        model.add(end_y == y + height)
        model.add_multiplication_equality(area, (width, height))
        model.add(area >= room.minimum_area_units)
        model.add(center_x2 == 2 * x + width)
        model.add(center_y2 == 2 * y + height)
        model.add_abs_equality(deviation, area - room.target_area_units)
        x_interval = model.new_interval_var(x, width, end_x, f"{prefix}_x_interval")
        y_interval = model.new_interval_var(y, height, end_y, f"{prefix}_y_interval")
        orientations = tuple(
            model.new_bool_var(f"{prefix}_orientation_{orientation}")
            for orientation in ORIENTATION_ORDER
        )
        model.add_exactly_one(orientations)
        model.add(end_y == boundary.height).only_enforce_if(orientations[0])
        model.add(end_x == boundary.width).only_enforce_if(orientations[1])
        model.add(y == 0).only_enforce_if(orientations[2])
        model.add(x == 0).only_enforce_if(orientations[3])
        model.add(x >= 1).only_enforce_if(orientations[4])
        model.add(y >= 1).only_enforce_if(orientations[4])
        model.add(end_x <= boundary.width - 1).only_enforce_if(orientations[4])
        model.add(end_y <= boundary.height - 1).only_enforce_if(orientations[4])
        result.append(
            RoomDecisionVariables(
                specification=room,
                x=x,
                y=y,
                width=width,
                height=height,
                end_x=end_x,
                end_y=end_y,
                area=area,
                center_x2=center_x2,
                center_y2=center_y2,
                target_area_deviation=deviation,
                x_interval=x_interval,
                y_interval=y_interval,
                orientation_literals=orientations,
            )
        )
    return tuple(result)


__all__ = ["ORIENTATION_ORDER", "RoomDecisionVariables", "create_room_variables"]
