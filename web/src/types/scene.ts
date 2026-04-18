// Scene types — hand-written to match spec/scene.schema.json v1.0.
// Kept separate from runtime validator so types surface at compile time.

export type Vec3 = [number, number, number];
export type Quat = [number, number, number, number];

export interface MaterialProps {
  friction: number;
  restitution: number;
}

export interface World {
  gravity: Vec3;
  up_axis: "y" | "z";
  unit: "meters";
}

export interface Ground {
  type: "plane";
  normal: Vec3;
  material: MaterialProps;
}

export interface Transform {
  translation: Vec3;
  rotation_quat: Quat;
  scale: number;
}

export type ColliderShape = "mesh" | "box" | "sphere" | "cylinder" | "capsule";

export interface Collider {
  shape: ColliderShape;
  convex_decomposition?: boolean;
  half_extents?: Vec3;
  radius?: number;
  height?: number;
}

export interface Physics {
  mass_kg: number;
  friction: number;
  restitution: number;
  is_rigid: boolean;
}

export interface Source {
  mesh_origin?: string;
  physics_origin?: "vlm" | "lookup" | "manual";
  vlm_reasoning?: string;
}

export interface SceneObject {
  id: string;
  class: string;
  mesh: string;
  transform: Transform;
  collider: Collider;
  physics: Physics;
  material_class: string;
  source?: Source;
}

export interface CameraPose {
  translation: Vec3;
  rotation_quat: Quat;
}

export interface SceneSpec {
  version: "1.0";
  world: World;
  ground: Ground;
  objects: SceneObject[];
  camera_pose?: CameraPose;
}

export type InteractionMode = "select" | "drag" | "drop_ball" | "apply_force";
