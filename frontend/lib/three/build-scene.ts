import * as THREE from "three";
import type {
  Point3,
  RenderIr,
  RenderObject,
  RoomRenderObject,
  WallRenderObject,
  OpeningRenderObject,
} from "../render-ir/types";

export interface BuiltWorldScene {
  readonly root: THREE.Group;
  readonly floorGroups: ReadonlyMap<string, THREE.Group>;
  readonly entityObjects: ReadonlyMap<string, THREE.Group>;
}

function roomMaterial(): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: 0xc8b78c,
    roughness: 0.88,
    metalness: 0,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.82,
  });
}

function wallMaterial(): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color: 0xebe6dc, roughness: 0.76, metalness: 0.02 });
}

function openingMaterial(entityType: "door" | "window"): THREE.MeshStandardMaterial {
  return entityType === "door"
    ? new THREE.MeshStandardMaterial({ color: 0xc66a45, roughness: 0.7, metalness: 0.02 })
    : new THREE.MeshStandardMaterial({
        color: 0x77a8b6,
        roughness: 0.35,
        metalness: 0.08,
        transparent: true,
        opacity: 0.8,
      });
}

function shapeFromRing(exterior: readonly Point3[], holes: readonly (readonly Point3[])[]): THREE.Shape {
  const shape = new THREE.Shape();
  const points = exterior.slice(0, -1);
  const first = points[0];
  if (!first) throw new Error("Render polygon has no exterior points.");
  shape.moveTo(first[0], first[1]);
  for (const point of points.slice(1)) shape.lineTo(point[0], point[1]);
  shape.closePath();

  for (const ring of holes) {
    const path = new THREE.Path();
    const holePoints = ring.slice(0, -1);
    const holeStart = holePoints[0];
    if (!holeStart) continue;
    path.moveTo(holeStart[0], holeStart[1]);
    for (const point of holePoints.slice(1)) path.lineTo(point[0], point[1]);
    path.closePath();
    shape.holes.push(path);
  }
  return shape;
}

function entityGroup(item: RenderObject): THREE.Group {
  const group = new THREE.Group();
  group.userData = {
    entityId: item.entity_id,
    entityType: item.entity_type,
    floorId: item.floor_id,
    selectable: true,
  };
  return group;
}

function roomObject(item: RoomRenderObject): THREE.Group {
  const group = entityGroup(item);
  const geometry = new THREE.ShapeGeometry(
    shapeFromRing(item.geometry.exterior, item.geometry.holes),
  );
  const mesh = new THREE.Mesh(geometry, roomMaterial());
  mesh.position.z = item.geometry.exterior[0]?.[2] ?? 0;
  mesh.receiveShadow = true;
  group.add(mesh);
  return group;
}

function wallObject(item: WallRenderObject): THREE.Group {
  const group = entityGroup(item);
  const geometry = new THREE.ExtrudeGeometry(
    shapeFromRing(item.geometry.footprint, []),
    {
      depth: item.geometry.height,
      bevelEnabled: false,
      curveSegments: 1,
      steps: 1,
    },
  );
  const mesh = new THREE.Mesh(geometry, wallMaterial());
  mesh.position.z = item.geometry.footprint[0]?.[2] ?? 0;
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  group.add(mesh);
  return group;
}

function openingObject(item: OpeningRenderObject): THREE.Group {
  const group = entityGroup(item);
  const { start, end, height, thickness } = item.geometry;
  const deltaX = end[0] - start[0];
  const deltaY = end[1] - start[1];
  const width = Math.hypot(deltaX, deltaY);
  const geometry = new THREE.BoxGeometry(width, thickness * 1.08, height);
  const mesh = new THREE.Mesh(geometry, openingMaterial(item.entity_type));
  mesh.position.set(
    (start[0] + end[0]) / 2,
    (start[1] + end[1]) / 2,
    start[2] + height / 2,
  );
  mesh.rotation.z = Math.atan2(deltaY, deltaX);
  mesh.castShadow = true;
  group.add(mesh);
  return group;
}

function buildObject(item: RenderObject): THREE.Group {
  if (item.entity_type === "room") return roomObject(item);
  if (item.entity_type === "wall") return wallObject(item);
  return openingObject(item);
}

export function buildWorldScene(renderIr: RenderIr): BuiltWorldScene {
  const root = new THREE.Group();
  const floorGroups = new Map<string, THREE.Group>();
  const entityObjects = new Map<string, THREE.Group>();

  for (const floor of renderIr.floors) {
    const group = new THREE.Group();
    group.userData = { floorId: floor.entity_id, entityType: "floor" };
    floorGroups.set(floor.entity_id, group);
    root.add(group);
  }

  for (const item of renderIr.objects) {
    const group = buildObject(item);
    floorGroups.get(item.floor_id)?.add(group);
    entityObjects.set(item.entity_id, group);
  }
  return { root, floorGroups, entityObjects };
}

export function resolveEntityObject(object: THREE.Object3D | null): THREE.Object3D | null {
  let current = object;
  while (current) {
    if (current.userData.selectable === true && typeof current.userData.entityId === "string") {
      return current;
    }
    current = current.parent;
  }
  return null;
}
