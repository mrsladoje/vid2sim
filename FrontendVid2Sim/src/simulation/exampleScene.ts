import type { SceneSpec } from "./types";

export const EXAMPLE_SCENE: SceneSpec = {
  version: "1.0",
  world: { gravity: [0, -9.81, 0], up_axis: "y", unit: "meters" },
  ground: {
    type: "plane",
    normal: [0, 1, 0],
    material: { friction: 0.8, restitution: 0.1 },
  },
  camera_pose: {
    translation: [3.2, 2.4, 3.6],
    rotation_quat: [0, 0, 0, 1],
  },
  objects: [
    {
      id: "table_01",
      class: "table",
      mesh: "primitive:table",
      material_class: "wood",
      transform: { translation: [0, 0.4, 0], rotation_quat: [0, 0, 0, 1], scale: 1 },
      collider: { shape: "box", half_extents: [0.6, 0.025, 0.4] },
      physics: { mass_kg: 18, friction: 0.7, restitution: 0.1, is_rigid: false },
      source: {
        mesh_origin: "TripoSG",
        physics_origin: "vlm",
        vlm_reasoning:
          "Dark-oak dining table; dense wood, low bounce, high friction. Treated as static for stability.",
      },
    },
    {
      id: "chair_01",
      class: "chair",
      mesh: "primitive:chair",
      material_class: "wood",
      transform: {
        translation: [-1.1, 0.5, 0.2],
        rotation_quat: [0, 0.38, 0, 0.92],
        scale: 1,
      },
      collider: { shape: "box", half_extents: [0.24, 0.32, 0.24] },
      physics: { mass_kg: 6, friction: 0.6, restitution: 0.15, is_rigid: true },
      source: {
        mesh_origin: "TripoSG",
        physics_origin: "vlm",
        vlm_reasoning: "Wooden chair, moderate weight; rigid body so it can be pushed around.",
      },
    },
    {
      id: "mug_01",
      class: "mug",
      mesh: "primitive:cylinder",
      material_class: "ceramic",
      transform: { translation: [0.25, 0.5, 0.1], rotation_quat: [0, 0, 0, 1], scale: 1 },
      collider: { shape: "cylinder", radius: 0.045, height: 0.1 },
      physics: { mass_kg: 0.35, friction: 0.45, restitution: 0.2, is_rigid: true },
      source: {
        mesh_origin: "Hunyuan3D",
        physics_origin: "lookup",
        vlm_reasoning: "Ceramic coffee mug; stiff, moderate bounce, tips easily when pushed.",
      },
    },
    {
      id: "book_01",
      class: "book",
      mesh: "primitive:box",
      material_class: "paper",
      transform: {
        translation: [-0.25, 0.44, -0.08],
        rotation_quat: [0, 0.13, 0, 0.99],
        scale: 1,
      },
      collider: { shape: "box", half_extents: [0.11, 0.02, 0.15] },
      physics: { mass_kg: 0.6, friction: 0.5, restitution: 0.05, is_rigid: true },
      source: {
        mesh_origin: "TripoSG",
        physics_origin: "vlm",
        vlm_reasoning:
          "Hardcover book; low bounce, medium friction. Small mass means it slides easily under impulse.",
      },
    },
    {
      id: "ball_01",
      class: "ball",
      mesh: "primitive:sphere",
      material_class: "rubber",
      transform: { translation: [-0.15, 0.6, 0.18], rotation_quat: [0, 0, 0, 1], scale: 1 },
      collider: { shape: "sphere", radius: 0.06 },
      physics: { mass_kg: 0.12, friction: 0.6, restitution: 0.85, is_rigid: true },
      source: {
        mesh_origin: "Hunyuan3D",
        physics_origin: "lookup",
        vlm_reasoning: "Rubber ball, high restitution. Bounces visibly on the table.",
      },
    },
    {
      id: "can_01",
      class: "can",
      mesh: "primitive:cylinder",
      material_class: "metal",
      transform: {
        translation: [0.42, 0.5, -0.12],
        rotation_quat: [0, 0, 0, 1],
        scale: 1,
      },
      collider: { shape: "cylinder", radius: 0.032, height: 0.12 },
      physics: { mass_kg: 0.4, friction: 0.4, restitution: 0.25, is_rigid: true },
      source: {
        mesh_origin: "TripoSG",
        physics_origin: "lookup",
        vlm_reasoning: "Aluminum can. Light, moderate bounce, rolls if pushed sideways.",
      },
    },
    {
      id: "crate_01",
      class: "crate",
      mesh: "primitive:box",
      material_class: "wood",
      transform: { translation: [1.3, 0.2, -1.0], rotation_quat: [0, 0, 0, 1], scale: 1 },
      collider: { shape: "box", half_extents: [0.2, 0.2, 0.2] },
      physics: { mass_kg: 4.5, friction: 0.75, restitution: 0.1, is_rigid: true },
      source: {
        mesh_origin: "TripoSG",
        physics_origin: "vlm",
        vlm_reasoning: "Wooden storage crate. Solid, heavy; resists being pushed.",
      },
    },
  ],
};
