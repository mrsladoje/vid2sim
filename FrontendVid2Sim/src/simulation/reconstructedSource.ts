import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type {
  LoadedMesh,
  LoadedScene,
  SceneSource,
  Vec3,
} from "./types";

/** Shape of a single entry in reconstructed.json (spec/reconstructed_object.md). */
export interface ReconstructedObjectEntry {
  id: string;
  class: string;
  mesh_path: string;
  crop_image_path?: string;
  mesh_origin: string;
  center: Vec3;
  rotation_quat: [number, number, number, number];
  bbox_min: Vec3;
  bbox_max: Vec3;
  lowest_points?: Vec3[];
}

export interface ReconstructedManifest {
  session_id: string;
  objects: ReconstructedObjectEntry[];
}

export interface ReconstructedJsonSourceOptions {
  /** URL to reconstructed.json (its folder becomes the base for mesh_path). */
  manifestUrl: string;
  /** Optional fetch override for tests. */
  fetchImpl?: typeof fetch;
  /** Optional GLTFLoader override for tests / offline asset resolution. */
  gltfLoader?: GLTFLoader;
  /** Optional display name override. Defaults to the manifest's session_id. */
  displayName?: string;
}

/**
 * Loader that consumes `reconstructed.json` + per-object `.glb` files.
 *
 * Notes on transforms (see spec/reconstructed_object.md §3):
 *   - `center` is a world-frame translation (metres)
 *   - `rotation_quat` is world-frame [x, y, z, w]
 *   - `bbox_min` / `bbox_max` are the AABB of the ALREADY-aligned mesh in
 *     world frame — i.e. the .glb already has an intrinsic transform baked
 *     in such that placing its root at `center` + `rotation_quat` lines up.
 *
 * To preserve the glTF's baked PBR textures we apply position + quaternion
 * to the root Object3D only, never touch the child tree.
 */
export class ReconstructedJsonSource implements SceneSource {
  readonly kind = "reconstructed" as const;
  readonly displayName: string;
  private readonly manifestUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly gltfLoader: GLTFLoader;

  constructor(opts: ReconstructedJsonSourceOptions) {
    this.manifestUrl = opts.manifestUrl;
    this.fetchImpl = opts.fetchImpl ?? fetch.bind(globalThis);
    this.gltfLoader = opts.gltfLoader ?? new GLTFLoader();
    this.displayName = opts.displayName ?? "Reconstructed scene";
  }

  async load(): Promise<LoadedScene> {
    const manifest = await this.fetchManifest();
    const baseUrl = resolveBaseUrl(this.manifestUrl);
    const displayName = this.displayName ?? manifest.session_id;

    const meshes = await Promise.all(
      manifest.objects.map((entry) => this.loadOneMesh(entry, baseUrl)),
    );

    const groundY = computeGroundY(manifest.objects);
    const cameraHint = framingHint(manifest.objects, groundY);

    return {
      displayName,
      meshes,
      groundY,
      gravityY: -9.81,
      groundMaterial: { friction: 0.85, restitution: 0.1 },
      cameraHint,
      isFallback: false,
    };
  }

  private async fetchManifest(): Promise<ReconstructedManifest> {
    const res = await this.fetchImpl(this.manifestUrl);
    if (!res.ok) {
      throw new ReconstructedFetchError(
        `Failed to fetch reconstructed manifest at ${this.manifestUrl}: HTTP ${res.status}`,
        res.status,
        this.manifestUrl,
      );
    }
    const json = (await res.json()) as ReconstructedManifest;
    validateManifest(json, this.manifestUrl);
    return json;
  }

  private async loadOneMesh(
    entry: ReconstructedObjectEntry,
    baseUrl: string,
  ): Promise<LoadedMesh> {
    const meshUrl = new URL(entry.mesh_path, baseUrl).toString();
    let root: THREE.Object3D;
    try {
      const gltf = await this.gltfLoader.loadAsync(meshUrl);
      root = gltf.scene ?? gltf.scenes?.[0];
      if (!root) {
        throw new Error(`glTF at ${meshUrl} has no scene`);
      }
    } catch (err) {
      console.error(
        `[ReconstructedJsonSource] mesh load failed for ${entry.id}`,
        { url: meshUrl, entry, err },
      );
      throw err;
    }

    root.traverse((c) => {
      const mesh = c as THREE.Mesh;
      if (mesh.isMesh) {
        mesh.castShadow = true;
        mesh.receiveShadow = true;
      }
    });

    const [cx, cy, cz] = entry.center;
    const [qx, qy, qz, qw] = entry.rotation_quat;
    root.position.set(cx, cy, cz);
    root.quaternion.set(qx, qy, qz, qw);
    tagWithId(root, entry.id);

    const bboxWorld = new THREE.Box3(
      new THREE.Vector3(...entry.bbox_min),
      new THREE.Vector3(...entry.bbox_max),
    );

    return {
      id: entry.id,
      object3d: root,
      label: prettyLabel(entry.class),
      classification: entry.class,
      bboxWorld,
      meshOrigin: entry.mesh_origin,
      physics: defaultPhysicsFor(entry.class),
    };
  }
}

export class ReconstructedFetchError extends Error {
  readonly status: number;
  readonly url: string;

  constructor(message: string, status: number, url: string) {
    super(message);
    this.name = "ReconstructedFetchError";
    this.status = status;
    this.url = url;
  }
}

// ---------------------------------------------------------------------------
// Helpers — exported for unit tests.
// ---------------------------------------------------------------------------

export function validateManifest(
  m: unknown,
  source: string,
): asserts m is ReconstructedManifest {
  if (!m || typeof m !== "object") {
    throw new Error(`reconstructed.json (${source}) is not an object`);
  }
  const mm = m as Partial<ReconstructedManifest>;
  if (!Array.isArray(mm.objects)) {
    throw new Error(`reconstructed.json (${source}) missing "objects" array`);
  }
  for (const [i, obj] of mm.objects.entries()) {
    if (!obj.id) throw new Error(`objects[${i}] missing id`);
    if (!obj.mesh_path) throw new Error(`objects[${i}] missing mesh_path`);
    if (!Array.isArray(obj.center) || obj.center.length !== 3)
      throw new Error(`objects[${i}] invalid center`);
    if (!Array.isArray(obj.rotation_quat) || obj.rotation_quat.length !== 4)
      throw new Error(`objects[${i}] invalid rotation_quat`);
    if (!Array.isArray(obj.bbox_min) || obj.bbox_min.length !== 3)
      throw new Error(`objects[${i}] invalid bbox_min`);
    if (!Array.isArray(obj.bbox_max) || obj.bbox_max.length !== 3)
      throw new Error(`objects[${i}] invalid bbox_max`);
  }
}

export function computeGroundY(objects: ReconstructedObjectEntry[]): number {
  let lo = Number.POSITIVE_INFINITY;
  for (const obj of objects) {
    if (obj.lowest_points && obj.lowest_points.length > 0) {
      for (const p of obj.lowest_points) {
        if (p[1] < lo) lo = p[1];
      }
    } else {
      if (obj.bbox_min[1] < lo) lo = obj.bbox_min[1];
    }
  }
  return Number.isFinite(lo) ? lo : 0;
}

export function resolveBaseUrl(manifestUrl: string): string {
  try {
    return new URL(".", manifestUrl).toString();
  } catch {
    // Relative URL in test environments — build an absolute one against the origin.
    const origin =
      typeof window !== "undefined" && window.location
        ? window.location.origin
        : "http://localhost/";
    return new URL(".", new URL(manifestUrl, origin)).toString();
  }
}

/** Camera hint: back off from the centroid by twice the scene diagonal. */
function framingHint(
  objects: ReconstructedObjectEntry[],
  groundY: number,
): LoadedScene["cameraHint"] {
  if (objects.length === 0) {
    return { position: [2, 1.5, 2], target: [0, groundY, 0] };
  }
  const min = new THREE.Vector3(
    Number.POSITIVE_INFINITY,
    Number.POSITIVE_INFINITY,
    Number.POSITIVE_INFINITY,
  );
  const max = new THREE.Vector3(
    Number.NEGATIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
  );
  for (const obj of objects) {
    min.min(new THREE.Vector3(...obj.bbox_min));
    max.max(new THREE.Vector3(...obj.bbox_max));
  }
  const center = min.clone().add(max).multiplyScalar(0.5);
  const size = max.clone().sub(min);
  const diag = Math.max(size.length(), 0.25);
  const back = Math.max(diag * 2.5, 0.8);
  const target: Vec3 = [center.x, Math.max(center.y, groundY + 0.05), center.z];
  const position: Vec3 = [center.x + back * 0.7, groundY + back * 0.8, center.z + back * 0.9];
  return { position, target };
}

/**
 * Rough physics defaults by class. Real physics values arrive via Stream 03's
 * scene.json with VLM reasoning; until then we pick conservative rigids for
 * common tabletop objects.
 */
function defaultPhysicsFor(cls: string) {
  const lowered = cls.toLowerCase();
  const presets: Record<string, { massKg: number; friction: number; restitution: number }> = {
    bottle: { massKg: 0.5, friction: 0.45, restitution: 0.2 },
    cup: { massKg: 0.35, friction: 0.45, restitution: 0.2 },
    mug: { massKg: 0.35, friction: 0.45, restitution: 0.2 },
    book: { massKg: 0.6, friction: 0.5, restitution: 0.05 },
    ball: { massKg: 0.15, friction: 0.6, restitution: 0.8 },
    can: { massKg: 0.4, friction: 0.4, restitution: 0.25 },
  };
  const preset = presets[lowered] ?? { massKg: 0.5, friction: 0.5, restitution: 0.15 };
  return { isRigid: true, ...preset };
}

function prettyLabel(cls: string): string {
  if (!cls) return "Object";
  return cls.charAt(0).toUpperCase() + cls.slice(1);
}

function tagWithId(root: THREE.Object3D, id: string) {
  root.userData.objectId = id;
  root.traverse((c) => {
    c.userData.objectId = id;
  });
}
