import { describe, expect, it } from "vitest";

import { parseRenderIr, RenderIrContractError } from "../lib/render-ir/parse";
import { validRenderIrInput } from "./fixtures";

function expectContractError(value: unknown, path: string): void {
  try {
    parseRenderIr(value);
    throw new Error("Expected the Render IR contract to reject the value.");
  } catch (error) {
    expect(error).toBeInstanceOf(RenderIrContractError);
    expect((error as RenderIrContractError).path).toBe(path);
  }
}

describe("parseRenderIr", () => {
  it("accepts the v1 contract and preserves the authoritative source metadata", () => {
    const result = parseRenderIr(validRenderIrInput());

    expect(result.render_ir_version).toBe("1.0.0");
    expect(result.source_model).toEqual({
      schema_version: "1.0.0",
      model_id: "model-test",
      revision: 7,
      root_building_id: "building-1",
    });
    expect(result.coordinate_system).toMatchObject({
      type: "local_cartesian",
      handedness: "right",
      up_axis: "Z",
    });
    expect(result.floors).toHaveLength(2);
    expect(result.objects.map((item) => item.entity_id)).toEqual([
      "room-ground",
      "wall-south",
      "door-entry",
      "window-south",
      "room-upper",
    ]);
  });

  it("deep-freezes the parsed snapshot", () => {
    const result = parseRenderIr(validRenderIrInput());

    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.source_model)).toBe(true);
    expect(Object.isFrozen(result.objects)).toBe(true);
    expect(Object.isFrozen(result.objects[0])).toBe(true);
    const room = result.objects[0];
    if (!room || room.entity_type !== "room") throw new Error("Fixture room is missing.");
    expect(Object.isFrozen(room.geometry)).toBe(true);
    expect(Object.isFrozen(room.geometry.exterior)).toBe(true);
    expect(Object.isFrozen(room.geometry.exterior[0])).toBe(true);

    expect(() => {
      (result.source_model as { revision: number }).revision = 99;
    }).toThrow(TypeError);
    expect(result.source_model.revision).toBe(7);
  });

  it("rejects unsupported Render IR versions", () => {
    const input = validRenderIrInput();
    input.render_ir_version = "2.0.0";

    expectContractError(input, "/render_ir_version");
  });

  it("rejects non-finite geometry and bounds values", () => {
    const geometryInput = validRenderIrInput();
    const room = geometryInput.objects[0];
    if (!room || room.entity_type !== "room") throw new Error("Fixture room is missing.");
    room.geometry.exterior[1]![0] = Number.POSITIVE_INFINITY;
    expectContractError(geometryInput, "/objects/0/geometry/exterior/1/0");

    const boundsInput = validRenderIrInput();
    boundsInput.bounds.max[2] = Number.NaN;
    expectContractError(boundsInput, "/bounds/max/2");
  });

  it("rejects duplicate entity IDs across floors and render objects", () => {
    const duplicateFloor = validRenderIrInput();
    duplicateFloor.floors[1]!.entity_id = duplicateFloor.floors[0]!.entity_id;
    expectContractError(duplicateFloor, "/floors");

    const duplicateObject = validRenderIrInput();
    duplicateObject.objects[1]!.entity_id = duplicateObject.objects[0]!.entity_id;
    expectContractError(duplicateObject, "/objects");

    const crossKindDuplicate = validRenderIrInput();
    crossKindDuplicate.objects[0]!.entity_id = crossKindDuplicate.floors[0]!.entity_id;
    expectContractError(crossKindDuplicate, "/objects");
  });

  it("rejects unknown floor and opening host references", () => {
    const unknownFloor = validRenderIrInput();
    unknownFloor.objects[0]!.floor_id = "floor-missing";
    expectContractError(unknownFloor, "/objects");

    const unknownHost = validRenderIrInput();
    const door = unknownHost.objects[2];
    if (!door || door.entity_type !== "door") throw new Error("Fixture door is missing.");
    door.host_wall_id = "wall-missing";
    expectContractError(unknownHost, "/objects");

    const crossFloorHost = validRenderIrInput();
    const crossFloorDoor = crossFloorHost.objects[2];
    if (!crossFloorDoor || crossFloorDoor.entity_type !== "door") {
      throw new Error("Fixture door is missing.");
    }
    crossFloorDoor.floor_id = "floor-upper";
    expectContractError(crossFloorHost, "/objects");
  });

  it("rejects floor, object, and point counts beyond the resource budgets", () => {
    const tooManyFloors = validRenderIrInput();
    const baseFloor = tooManyFloors.floors[0]!;
    tooManyFloors.floors = Array.from({ length: 129 }, (_, index) => ({
      ...baseFloor,
      entity_id: `floor-${index}`,
    }));
    expectContractError(tooManyFloors, "/floors");

    const tooManyObjects = validRenderIrInput();
    tooManyObjects.objects = Array.from(
      { length: 10_001 },
      () => tooManyObjects.objects[0]!,
    );
    expectContractError(tooManyObjects, "/objects");

    const tooManyPoints = validRenderIrInput();
    const room = tooManyPoints.objects[0];
    if (!room || room.entity_type !== "room") throw new Error("Fixture room is missing.");
    room.geometry.exterior = Array.from({ length: 100_001 }, (_, index) => [index, 0, 0]);
    expectContractError(tooManyPoints, "/objects/0/geometry/exterior/100000");
  });
});
