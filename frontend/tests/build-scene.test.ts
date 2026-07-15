import * as THREE from "three";
import { afterEach, describe, expect, it } from "vitest";

import { buildWorldScene, resolveEntityObject } from "../lib/three/build-scene";
import { disposeObjectTree } from "../lib/three/dispose";
import { validRenderIr } from "./fixtures";

const roots: THREE.Object3D[] = [];

afterEach(() => {
  for (const root of roots.splice(0)) disposeObjectTree(root);
});

describe("buildWorldScene", () => {
  it("maps every Render IR floor and object to stable Three.js groups", () => {
    const renderIr = validRenderIr();
    const built = buildWorldScene(renderIr);
    roots.push(built.root);

    expect(built.root).toBeInstanceOf(THREE.Group);
    expect(built.floorGroups.size).toBe(renderIr.floors.length);
    expect(built.entityObjects.size).toBe(renderIr.objects.length);
    expect(built.root.children).toEqual([
      built.floorGroups.get("floor-ground"),
      built.floorGroups.get("floor-upper"),
    ]);

    const ground = built.floorGroups.get("floor-ground");
    const upper = built.floorGroups.get("floor-upper");
    expect(ground?.userData).toMatchObject({ floorId: "floor-ground", entityType: "floor" });
    expect(ground?.children).toHaveLength(4);
    expect(upper?.children).toHaveLength(1);

    const wall = built.entityObjects.get("wall-south");
    expect(wall?.parent).toBe(ground);
    expect(wall?.userData).toEqual({
      entityId: "wall-south",
      entityType: "wall",
      floorId: "floor-ground",
      selectable: true,
    });
  });

  it("builds Z-up room, extrusion, and opening geometry at contract coordinates", () => {
    const built = buildWorldScene(validRenderIr());
    roots.push(built.root);

    const upperRoom = built.entityObjects.get("room-upper");
    const roomMesh = upperRoom?.children[0];
    expect(roomMesh).toBeInstanceOf(THREE.Mesh);
    expect(roomMesh?.position.z).toBe(3);

    const wall = built.entityObjects.get("wall-south");
    const wallMesh = wall?.children[0];
    expect(wallMesh).toBeInstanceOf(THREE.Mesh);
    if (!(wallMesh instanceof THREE.Mesh)) throw new Error("Wall mesh is missing.");
    wallMesh.geometry.computeBoundingBox();
    expect(wallMesh.geometry.boundingBox?.min.z).toBeCloseTo(0);
    expect(wallMesh.geometry.boundingBox?.max.z).toBeCloseTo(3);
    expect(wallMesh.position.z).toBe(0);

    const door = built.entityObjects.get("door-entry");
    const doorMesh = door?.children[0];
    expect(doorMesh).toBeInstanceOf(THREE.Mesh);
    expect(doorMesh?.position.toArray()).toEqual([1.5, 0.1, 1.05]);
    expect(doorMesh?.rotation.z).toBeCloseTo(0);

    const windowObject = built.entityObjects.get("window-south");
    const windowMesh = windowObject?.children[0];
    expect(windowMesh?.position.toArray()).toEqual([3.75, 0.1, 1.6]);
  });
});

describe("resolveEntityObject", () => {
  it("walks from a mesh to its selectable entity group", () => {
    const built = buildWorldScene(validRenderIr());
    roots.push(built.root);
    const group = built.entityObjects.get("door-entry");
    const mesh = group?.children[0] ?? null;

    expect(resolveEntityObject(mesh)).toBe(group);
    expect(resolveEntityObject(group ?? null)).toBe(group);
    expect(resolveEntityObject(built.floorGroups.get("floor-ground") ?? null)).toBeNull();
    expect(resolveEntityObject(new THREE.Object3D())).toBeNull();
    expect(resolveEntityObject(null)).toBeNull();
  });
});
