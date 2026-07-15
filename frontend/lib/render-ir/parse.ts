import type {
  OpeningPanelGeometry,
  OpeningRenderObject,
  Point3,
  PolygonSurfaceGeometry,
  RenderBounds,
  RenderCoordinateSystem,
  RenderFloor,
  RenderIr,
  RenderObject,
  RenderSourceModel,
  RoomRenderObject,
  VerticalExtrusionGeometry,
  WallRenderObject,
} from "./types";

const MAX_FLOORS = 128;
const MAX_OBJECTS = 10_000;
const MAX_POINTS = 100_000;

export class RenderIrContractError extends Error {
  readonly path: string;

  constructor(message: string, path = "/") {
    super(message);
    this.name = "RenderIrContractError";
    this.path = path;
  }
}

interface Budget {
  points: number;
}

type JsonRecord = Record<string, unknown>;

function record(value: unknown, path: string): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new RenderIrContractError("Expected an object.", path);
  }
  return value as JsonRecord;
}

function exactKeys(value: JsonRecord, expected: readonly string[], path: string): void {
  const actual = Object.keys(value).sort();
  const canonical = [...expected].sort();
  if (actual.length !== canonical.length || actual.some((key, index) => key !== canonical[index])) {
    throw new RenderIrContractError("Object fields do not match the Render IR contract.", path);
  }
}

function string(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new RenderIrContractError("Expected a non-empty string.", path);
  }
  return value;
}

function finite(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new RenderIrContractError("Expected a finite number.", path);
  }
  return value;
}

function positive(value: unknown, path: string): number {
  const result = finite(value, path);
  if (result <= 0) throw new RenderIrContractError("Expected a positive number.", path);
  return result;
}

function literal<T extends string>(value: unknown, expected: T, path: string): T {
  if (value !== expected) {
    throw new RenderIrContractError(`Expected ${JSON.stringify(expected)}.`, path);
  }
  return expected;
}

function array(value: unknown, path: string): readonly unknown[] {
  if (!Array.isArray(value)) throw new RenderIrContractError("Expected an array.", path);
  return value;
}

function point(value: unknown, path: string, budget?: Budget): Point3 {
  const values = array(value, path);
  if (values.length !== 3) throw new RenderIrContractError("Expected a 3D point.", path);
  if (budget) {
    budget.points += 1;
    if (budget.points > MAX_POINTS) {
      throw new RenderIrContractError("Render IR point budget exceeded.", path);
    }
  }
  return [
    finite(values[0], `${path}/0`),
    finite(values[1], `${path}/1`),
    finite(values[2], `${path}/2`),
  ];
}

function ring(value: unknown, path: string, budget: Budget): readonly Point3[] {
  const values = array(value, path);
  if (values.length < 4) throw new RenderIrContractError("A ring needs at least four points.", path);
  const result = values.map((item, index) => point(item, `${path}/${index}`, budget));
  const first = result[0];
  const last = result[result.length - 1];
  if (!first || !last || first.some((coordinate, index) => coordinate !== last[index])) {
    throw new RenderIrContractError("A ring must be closed.", path);
  }
  if (result.some((item) => item[2] !== first[2])) {
    throw new RenderIrContractError("A render ring must be horizontal.", path);
  }
  return result;
}

function sourceModel(value: unknown): RenderSourceModel {
  const item = record(value, "/source_model");
  exactKeys(item, ["schema_version", "model_id", "revision", "root_building_id"], "/source_model");
  const revision = finite(item.revision, "/source_model/revision");
  if (!Number.isSafeInteger(revision) || revision < 0) {
    throw new RenderIrContractError("Revision must be a non-negative safe integer.", "/source_model/revision");
  }
  return {
    schema_version: string(item.schema_version, "/source_model/schema_version"),
    model_id: string(item.model_id, "/source_model/model_id"),
    revision,
    root_building_id: string(item.root_building_id, "/source_model/root_building_id"),
  };
}

function coordinateSystem(value: unknown): RenderCoordinateSystem {
  const item = record(value, "/coordinate_system");
  exactKeys(item, ["type", "handedness", "up_axis", "origin"], "/coordinate_system");
  return {
    type: literal(item.type, "local_cartesian", "/coordinate_system/type"),
    handedness: literal(item.handedness, "right", "/coordinate_system/handedness"),
    up_axis: literal(item.up_axis, "Z", "/coordinate_system/up_axis"),
    origin: point(item.origin, "/coordinate_system/origin"),
  };
}

function bounds(value: unknown): RenderBounds {
  const item = record(value, "/bounds");
  exactKeys(item, ["min", "max"], "/bounds");
  const minimum = point(item.min, "/bounds/min");
  const maximum = point(item.max, "/bounds/max");
  if (minimum.some((coordinate, index) => coordinate > maximum[index])) {
    throw new RenderIrContractError("Bounds minimum cannot exceed maximum.", "/bounds");
  }
  return { min: minimum, max: maximum };
}

function floor(value: unknown, index: number): RenderFloor {
  const path = `/floors/${index}`;
  const item = record(value, path);
  exactKeys(item, ["entity_id", "entity_type", "name", "elevation", "height"], path);
  return {
    entity_id: string(item.entity_id, `${path}/entity_id`),
    entity_type: literal(item.entity_type, "floor", `${path}/entity_type`),
    name: string(item.name, `${path}/name`),
    elevation: finite(item.elevation, `${path}/elevation`),
    height: positive(item.height, `${path}/height`),
  };
}

function polygon(value: unknown, path: string, budget: Budget): PolygonSurfaceGeometry {
  const item = record(value, path);
  exactKeys(item, ["kind", "exterior", "holes"], path);
  literal(item.kind, "polygon_surface", `${path}/kind`);
  const exterior = ring(item.exterior, `${path}/exterior`, budget);
  const holes = array(item.holes, `${path}/holes`).map((item, index) =>
    ring(item, `${path}/holes/${index}`, budget),
  );
  if (holes.some((hole) => hole[0]?.[2] !== exterior[0]?.[2])) {
    throw new RenderIrContractError("Polygon rings must share one elevation.", path);
  }
  return { kind: "polygon_surface", exterior, holes };
}

function extrusion(value: unknown, path: string, budget: Budget): VerticalExtrusionGeometry {
  const item = record(value, path);
  exactKeys(item, ["kind", "footprint", "height"], path);
  literal(item.kind, "vertical_extrusion", `${path}/kind`);
  return {
    kind: "vertical_extrusion",
    footprint: ring(item.footprint, `${path}/footprint`, budget),
    height: positive(item.height, `${path}/height`),
  };
}

function openingPanel(value: unknown, path: string, budget: Budget): OpeningPanelGeometry {
  const item = record(value, path);
  exactKeys(item, ["kind", "start", "end", "height", "thickness"], path);
  literal(item.kind, "opening_panel", `${path}/kind`);
  const start = point(item.start, `${path}/start`, budget);
  const end = point(item.end, `${path}/end`, budget);
  if (start[2] !== end[2] || start.every((coordinate, index) => coordinate === end[index])) {
    throw new RenderIrContractError("Opening endpoints must define a horizontal non-zero panel.", path);
  }
  return {
    kind: "opening_panel",
    start,
    end,
    height: positive(item.height, `${path}/height`),
    thickness: positive(item.thickness, `${path}/thickness`),
  };
}

function renderObject(value: unknown, index: number, budget: Budget): RenderObject {
  const path = `/objects/${index}`;
  const item = record(value, path);
  const entityType = string(item.entity_type, `${path}/entity_type`);
  if (entityType === "room") {
    exactKeys(item, ["entity_id", "entity_type", "floor_id", "name", "geometry"], path);
    const result: RoomRenderObject = {
      entity_id: string(item.entity_id, `${path}/entity_id`),
      entity_type: "room",
      floor_id: string(item.floor_id, `${path}/floor_id`),
      name: string(item.name, `${path}/name`),
      geometry: polygon(item.geometry, `${path}/geometry`, budget),
    };
    return result;
  }
  if (entityType === "wall") {
    exactKeys(item, ["entity_id", "entity_type", "floor_id", "name", "geometry"], path);
    const result: WallRenderObject = {
      entity_id: string(item.entity_id, `${path}/entity_id`),
      entity_type: "wall",
      floor_id: string(item.floor_id, `${path}/floor_id`),
      name: string(item.name, `${path}/name`),
      geometry: extrusion(item.geometry, `${path}/geometry`, budget),
    };
    return result;
  }
  if (entityType === "door" || entityType === "window") {
    exactKeys(
      item,
      ["entity_id", "entity_type", "floor_id", "name", "host_wall_id", "geometry"],
      path,
    );
    const result: OpeningRenderObject = {
      entity_id: string(item.entity_id, `${path}/entity_id`),
      entity_type: entityType,
      floor_id: string(item.floor_id, `${path}/floor_id`),
      name: string(item.name, `${path}/name`),
      host_wall_id: string(item.host_wall_id, `${path}/host_wall_id`),
      geometry: openingPanel(item.geometry, `${path}/geometry`, budget),
    };
    return result;
  }
  throw new RenderIrContractError("Unsupported render object type.", `${path}/entity_type`);
}

function validateReferences(floors: readonly RenderFloor[], objects: readonly RenderObject[]): void {
  const floorIds = new Set<string>();
  for (const item of floors) {
    if (floorIds.has(item.entity_id)) {
      throw new RenderIrContractError("Duplicate floor entity ID.", "/floors");
    }
    floorIds.add(item.entity_id);
  }
  const objectIds = new Set<string>();
  const walls = new Map<string, WallRenderObject>();
  for (const item of objects) {
    if (objectIds.has(item.entity_id) || floorIds.has(item.entity_id)) {
      throw new RenderIrContractError("Duplicate render entity ID.", "/objects");
    }
    if (!floorIds.has(item.floor_id)) {
      throw new RenderIrContractError("Render object references an unknown floor.", "/objects");
    }
    objectIds.add(item.entity_id);
    if (item.entity_type === "wall") walls.set(item.entity_id, item);
  }
  for (const item of objects) {
    if (item.entity_type !== "door" && item.entity_type !== "window") continue;
    const host = walls.get(item.host_wall_id);
    if (!host || host.floor_id !== item.floor_id) {
      throw new RenderIrContractError("Opening references an unknown host wall.", "/objects");
    }
  }
}

function deepFreeze<T>(value: T): T {
  if (typeof value !== "object" || value === null || Object.isFrozen(value)) return value;
  for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child);
  return Object.freeze(value);
}

export function parseRenderIr(value: unknown): RenderIr {
  const root = record(value, "/");
  exactKeys(
    root,
    ["render_ir_version", "source_model", "units", "coordinate_system", "bounds", "floors", "objects"],
    "/",
  );
  literal(root.render_ir_version, "1.0.0", "/render_ir_version");
  const unitValues = record(root.units, "/units");
  exactKeys(unitValues, ["length", "angle"], "/units");
  literal(unitValues.length, "m", "/units/length");
  literal(unitValues.angle, "degree", "/units/angle");

  const floorValues = array(root.floors, "/floors");
  if (floorValues.length === 0 || floorValues.length > MAX_FLOORS) {
    throw new RenderIrContractError("Render IR floor count is outside the supported budget.", "/floors");
  }
  const objectValues = array(root.objects, "/objects");
  if (objectValues.length === 0 || objectValues.length > MAX_OBJECTS) {
    throw new RenderIrContractError("Render IR object count is outside the supported budget.", "/objects");
  }
  const pointBudget: Budget = { points: 0 };
  const floors = floorValues.map(floor);
  const objects = objectValues.map((item, index) => renderObject(item, index, pointBudget));
  validateReferences(floors, objects);

  return deepFreeze({
    render_ir_version: "1.0.0",
    source_model: sourceModel(root.source_model),
    units: { length: "m", angle: "degree" },
    coordinate_system: coordinateSystem(root.coordinate_system),
    bounds: bounds(root.bounds),
    floors,
    objects,
  });
}
