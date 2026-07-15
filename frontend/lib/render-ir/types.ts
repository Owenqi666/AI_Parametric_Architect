export type Point3 = readonly [number, number, number];

export interface RenderSourceModel {
  readonly schema_version: string;
  readonly model_id: string;
  readonly revision: number;
  readonly root_building_id: string;
}

export interface RenderCoordinateSystem {
  readonly type: "local_cartesian";
  readonly handedness: "right";
  readonly up_axis: "Z";
  readonly origin: Point3;
}

export interface RenderBounds {
  readonly min: Point3;
  readonly max: Point3;
}

export interface RenderFloor {
  readonly entity_id: string;
  readonly entity_type: "floor";
  readonly name: string;
  readonly elevation: number;
  readonly height: number;
}

export interface PolygonSurfaceGeometry {
  readonly kind: "polygon_surface";
  readonly exterior: readonly Point3[];
  readonly holes: readonly (readonly Point3[])[];
}

export interface VerticalExtrusionGeometry {
  readonly kind: "vertical_extrusion";
  readonly footprint: readonly Point3[];
  readonly height: number;
}

export interface OpeningPanelGeometry {
  readonly kind: "opening_panel";
  readonly start: Point3;
  readonly end: Point3;
  readonly height: number;
  readonly thickness: number;
}

interface RenderObjectBase {
  readonly entity_id: string;
  readonly floor_id: string;
  readonly name: string;
}

export interface RoomRenderObject extends RenderObjectBase {
  readonly entity_type: "room";
  readonly geometry: PolygonSurfaceGeometry;
}

export interface WallRenderObject extends RenderObjectBase {
  readonly entity_type: "wall";
  readonly geometry: VerticalExtrusionGeometry;
}

export interface OpeningRenderObject extends RenderObjectBase {
  readonly entity_type: "door" | "window";
  readonly host_wall_id: string;
  readonly geometry: OpeningPanelGeometry;
}

export type RenderObject = RoomRenderObject | WallRenderObject | OpeningRenderObject;

export interface RenderIr {
  readonly render_ir_version: "1.0.0";
  readonly source_model: RenderSourceModel;
  readonly units: {
    readonly length: "m";
    readonly angle: "degree";
  };
  readonly coordinate_system: RenderCoordinateSystem;
  readonly bounds: RenderBounds;
  readonly floors: readonly RenderFloor[];
  readonly objects: readonly RenderObject[];
}
