import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type {
  LoadedMesh,
  LoadedScene,
  SceneObject,
  SceneSource,
  SceneSpec,
} from "./types";
import { buildPrimitiveMesh } from "./primitives";

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

/**
 * Wraps the hand-crafted demo scene as a SceneSource. Primitive meshes are
 * built inline; any "mesh:<url>" entries would fall through to GLTFLoader.
 */
export class ExampleSceneSource implements SceneSource {
  readonly kind = "demo" as const;
  readonly displayName = "Demo scene";
  private readonly spec: SceneSpec;
  private readonly isFallback: boolean;

  constructor(spec: SceneSpec = EXAMPLE_SCENE, isFallback = false) {
    this.spec = spec;
    this.isFallback = isFallback;
  }

  async load(): Promise<LoadedScene> {
    const meshes: LoadedMesh[] = [];
    for (const obj of this.spec.objects) {
      const root = await buildMeshForSpec(obj);
      const t = obj.transform.translation;
      const q = obj.transform.rotation_quat;
      root.position.set(t[0], t[1], t[2]);
      root.quaternion.set(q[0], q[1], q[2], q[3]);
      if (obj.transform.scale !== 1.0) root.scale.setScalar(obj.transform.scale);
      tagWithId(root, obj.id);

      const bbox = new THREE.Box3().setFromObject(root);

      meshes.push({
        id: obj.id,
        object3d: root,
        label: prettyLabel(obj.class),
        classification: obj.class,
        bboxWorld: bbox,
        meshOrigin: obj.source?.mesh_origin ?? "primitive",
        physics: {
          isRigid: obj.physics.is_rigid,
          massKg: obj.physics.mass_kg,
          friction: obj.physics.friction,
          restitution: obj.physics.restitution,
        },
        legacySpec: obj,
      });
    }

    return {
      displayName: this.displayName,
      meshes,
      groundY: 0,
      gravityY: this.spec.world.gravity[1],
      groundMaterial: this.spec.ground.material,
      cameraHint: this.spec.camera_pose && {
        position: this.spec.camera_pose.translation,
        target: [0, 0.4, 0],
      },
      isFallback: this.isFallback,
    };
  }
}

async function buildMeshForSpec(obj: SceneObject): Promise<THREE.Object3D> {
  if (obj.mesh.startsWith("primitive:")) return buildPrimitiveMesh(obj);
  try {
    const loader = new GLTFLoader();
    const gltf = await loader.loadAsync(obj.mesh);
    const root = gltf.scene ?? gltf.scenes?.[0];
    if (!root) throw new Error(`glTF at ${obj.mesh} has no scene`);
    root.traverse((c) => {
      const mesh = c as THREE.Mesh;
      if (mesh.isMesh) {
        mesh.castShadow = true;
        mesh.receiveShadow = true;
      }
    });
    return root;
  } catch (e) {
    console.warn(`mesh ${obj.mesh} failed to load; falling back to primitive`, e);
    return buildPrimitiveMesh({ ...obj, mesh: `primitive:${obj.collider.shape}` });
  }
}

function tagWithId(root: THREE.Object3D, id: string) {
  root.userData.objectId = id;
  root.traverse((c) => {
    c.userData.objectId = id;
  });
}

function prettyLabel(cls: string): string {
  if (!cls) return "Object";
  return cls.charAt(0).toUpperCase() + cls.slice(1);
}
