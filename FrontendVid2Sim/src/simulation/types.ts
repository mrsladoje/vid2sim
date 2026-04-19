import type * as THREE from "three";

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

// ---------------------------------------------------------------------------
// SceneSource — the abstraction the viewer renders against.
// Each implementation (ExampleSceneSource, ReconstructedJsonSource, future
// SceneJsonSource for Stream 03's scene.gltf) resolves its own inputs and
// hands back a uniform LoadedScene. Viewer.ts + physics.ts never branch on
// the underlying data format.
// ---------------------------------------------------------------------------

export interface LoadedMeshPhysics {
  isRigid: boolean;
  massKg: number;
  friction: number;
  restitution: number;
}

export interface LoadedMesh {
  id: string;
  /**
   * Root Object3D already placed in world coordinates. The viewer and physics
   * layer MUST NOT mutate the child tree — only read transforms / swap
   * materials at the root level. This preserves baked textures from glTF.
   */
  object3d: THREE.Object3D;
  label: string;
  classification: string;
  bboxWorld: THREE.Box3;
  meshOrigin: string;
  physics?: LoadedMeshPhysics;
  /** Optional passthrough to keep the existing inspector UI (VLM reasoning) working. */
  legacySpec?: SceneObject;
}

export interface CameraHint {
  position: Vec3;
  target: Vec3;
}

export interface LoadedScene {
  displayName: string;
  meshes: LoadedMesh[];
  groundY: number;
  gravityY: number;
  groundMaterial: MaterialProps;
  cameraHint?: CameraHint;
  /** true when the loader fell back to synthetic data (drives the "demo data" badge). */
  isFallback: boolean;
}

export type SceneSourceKind = "demo" | "reconstructed" | "scene-gltf";

export interface SceneSource {
  readonly displayName: string;
  readonly kind: SceneSourceKind;
  load(): Promise<LoadedScene>;
}
