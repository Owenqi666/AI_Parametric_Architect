import { parseRenderIr } from "../lib/render-ir/parse";
import type { RenderIr } from "../lib/render-ir/types";

interface InputFloor {
  entity_id: string;
  entity_type: string;
  name: string;
  elevation: number;
  height: number;
}

interface InputRoom {
  entity_id: string;
  entity_type: "room";
  floor_id: string;
  name: string;
  geometry: {
    kind: string;
    exterior: number[][];
    holes: number[][][];
  };
}

interface InputWall {
  entity_id: string;
  entity_type: "wall";
  floor_id: string;
  name: string;
  geometry: {
    kind: string;
    footprint: number[][];
    height: number;
  };
}

interface InputOpening {
  entity_id: string;
  entity_type: "door" | "window";
  floor_id: string;
  name: string;
  host_wall_id: string;
  geometry: {
    kind: string;
    start: number[];
    end: number[];
    height: number;
    thickness: number;
  };
}

type InputObject = InputRoom | InputWall | InputOpening;

export interface RenderIrInput {
  render_ir_version: string;
  source_model: {
    schema_version: string;
    model_id: string;
    revision: number;
    root_building_id: string;
  };
  units: { length: string; angle: string };
  coordinate_system: {
    type: string;
    handedness: string;
    up_axis: string;
    origin: number[];
  };
  bounds: { min: number[]; max: number[] };
  floors: InputFloor[];
  objects: InputObject[];
}

export function validRenderIrInput(): RenderIrInput {
  return {
    render_ir_version: "1.0.0",
    source_model: {
      schema_version: "1.0.0",
      model_id: "model-test",
      revision: 7,
      root_building_id: "building-1",
    },
    units: { length: "m", angle: "degree" },
    coordinate_system: {
      type: "local_cartesian",
      handedness: "right",
      up_axis: "Z",
      origin: [0, 0, 0],
    },
    bounds: { min: [0, 0, 0], max: [8, 6, 6] },
    floors: [
      {
        entity_id: "floor-ground",
        entity_type: "floor",
        name: "Ground floor",
        elevation: 0,
        height: 3,
      },
      {
        entity_id: "floor-upper",
        entity_type: "floor",
        name: "Upper floor",
        elevation: 3,
        height: 3,
      },
    ],
    objects: [
      {
        entity_id: "room-ground",
        entity_type: "room",
        floor_id: "floor-ground",
        name: "Ground room",
        geometry: {
          kind: "polygon_surface",
          exterior: [
            [0, 0, 0],
            [6, 0, 0],
            [6, 4, 0],
            [0, 4, 0],
            [0, 0, 0],
          ],
          holes: [],
        },
      },
      {
        entity_id: "wall-south",
        entity_type: "wall",
        floor_id: "floor-ground",
        name: "South wall",
        geometry: {
          kind: "vertical_extrusion",
          footprint: [
            [0, 0, 0],
            [6, 0, 0],
            [6, 0.2, 0],
            [0, 0.2, 0],
            [0, 0, 0],
          ],
          height: 3,
        },
      },
      {
        entity_id: "door-entry",
        entity_type: "door",
        floor_id: "floor-ground",
        name: "Entry door",
        host_wall_id: "wall-south",
        geometry: {
          kind: "opening_panel",
          start: [1, 0.1, 0],
          end: [2, 0.1, 0],
          height: 2.1,
          thickness: 0.2,
        },
      },
      {
        entity_id: "window-south",
        entity_type: "window",
        floor_id: "floor-ground",
        name: "South window",
        host_wall_id: "wall-south",
        geometry: {
          kind: "opening_panel",
          start: [3, 0.1, 1],
          end: [4.5, 0.1, 1],
          height: 1.2,
          thickness: 0.2,
        },
      },
      {
        entity_id: "room-upper",
        entity_type: "room",
        floor_id: "floor-upper",
        name: "Upper room",
        geometry: {
          kind: "polygon_surface",
          exterior: [
            [0, 0, 3],
            [5, 0, 3],
            [5, 3, 3],
            [0, 3, 3],
            [0, 0, 3],
          ],
          holes: [],
        },
      },
    ],
  };
}

export function validRenderIr(): RenderIr {
  return parseRenderIr(validRenderIrInput());
}
