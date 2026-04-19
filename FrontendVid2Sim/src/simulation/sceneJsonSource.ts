import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type {
  LoadedMesh,
  LoadedScene,
  SceneObject,
  SceneSource,
  SceneSpec,
} from "./types";

export interface SceneJsonSourceOptions {
  /** URL to scene.json (its folder becomes the base for `mesh` + `hull_paths`). */
  manifestUrl: string;
  fetchImpl?: typeof fetch;
  gltfLoader?: GLTFLoader;
  displayName?: string;
}

/**
 * Loader for Stream 03's assembled scene (spec/scene.schema.json v1.0).
 *
 * Bug-avoidance contract (see Stream 03 post-mortem):
 *   - Bug 2 (textures stripped): we never call force=mesh; GLTFLoader's
 *     Scene/Group is returned as-is; baked PBR atlases survive.
 *   - Bug 5 (double rotation): Stream 03 bakes world rotation into the
 *     staged mesh and writes transform.rotation_quat = (0,0,0,1). We still
 *     apply quat here for forward compatibility; identity is a no-op.
 *   - Bug 6 (dropped node transforms): we load each object's per-object
 *     mesh file (`meshes/<id>.glb`), whose internal node graph carries the
 *     staged transform. We never load the composed `scene.glb` monolith —
 *     that would weld everything into one Object3D and foreclose per-object
 *     physics.
 *   - Bug 4 (floating / below-ground): Stream 03 is supposed to snap meshes to
 *     ground. In practice some live sessions still arrive offset vertically, so
 *     we derive a fallback groundY from the loaded mesh bounds when needed.
 *
 * One LoadedMesh per scene object → one Rapier rigid body per object in
 * physics.ts. No monolithic bodies.
 */
export class SceneJsonSource implements SceneSource {
  readonly kind = "scene-gltf" as const;
  readonly displayName: string;
  private readonly manifestUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly gltfLoader: GLTFLoader;

  constructor(opts: SceneJsonSourceOptions) {
    this.manifestUrl = opts.manifestUrl;
    this.fetchImpl = opts.fetchImpl ?? fetch.bind(globalThis);
    this.gltfLoader = opts.gltfLoader ?? new GLTFLoader();
    this.displayName = opts.displayName ?? "Assembled scene";
  }

  async load(): Promise<LoadedScene> {
    const manifest = await this.fetchManifest();
    const baseUrl = resolveBaseUrl(this.manifestUrl);

    const meshes = await Promise.all(
      manifest.objects.map((obj) => this.loadOneMesh(obj, baseUrl)),
    );

    const groundNormal = manifest.ground?.normal ?? [0, 1, 0];
    if (groundNormal[1] < 0.99) {
      console.warn(
        "[SceneJsonSource] ground.normal is not +Y; viewer assumes y-up",
        { normal: groundNormal, source: this.manifestUrl },
      );
    }

    const groundY = deriveGroundY(meshes, this.manifestUrl);

    return {
      displayName: this.displayName,
      meshes,
      groundY,
      gravityY: manifest.world?.gravity?.[1] ?? -9.81,
      groundMaterial: manifest.ground?.material ?? { friction: 0.85, restitution: 0.1 },
      cameraHint: framingHint(meshes, groundY),
      isFallback: false,
    };
  }

  private async fetchManifest(): Promise<SceneSpec> {
    const res = await this.fetchImpl(this.manifestUrl, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      throw new SceneJsonFetchError(
        `Failed to fetch scene.json at ${this.manifestUrl}: HTTP ${res.status}`,
        res.status,
        this.manifestUrl,
      );
    }
    const ct = res.headers.get("content-type") ?? "";
    if (!ct.includes("json")) {
      throw new SceneJsonFetchError(
        `scene.json at ${this.manifestUrl} returned non-JSON (${ct || "no content-type"})`,
        res.status,
        this.manifestUrl,
      );
    }
    const json = (await res.json()) as SceneSpec;
    validateSceneSpec(json, this.manifestUrl);
    return json;
  }

  private async loadOneMesh(obj: SceneObject, baseUrl: string): Promise<LoadedMesh> {
    if (obj.mesh.startsWith("primitive:")) {
      throw new Error(
        `[SceneJsonSource] primitive mesh references are not supported here (${obj.id}); ` +
          `use ExampleSceneSource for the demo fallback`,
      );
    }

    const meshUrl = new URL(obj.mesh, baseUrl).toString();
    let root: THREE.Object3D;
    try {
      const gltf = await this.gltfLoader.loadAsync(meshUrl);
      root = gltf.scene ?? gltf.scenes?.[0];
      if (!root) throw new Error(`glTF at ${meshUrl} has no scene`);
    } catch (err) {
      console.error(
        `[SceneJsonSource] per-object mesh load failed for ${obj.id}`,
        { url: meshUrl, obj, err },
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

    // Apply ONLY transforms the assembler authored in scene.json. The staged
    // GLB's internal transform (from Stream 03's composed node transform) is
    // preserved untouched inside the Object3D child tree.
    const t = obj.transform.translation;
    const q = obj.transform.rotation_quat;
    root.position.set(t[0], t[1], t[2]);
    root.quaternion.set(q[0], q[1], q[2], q[3]);
    if (obj.transform.scale !== 1.0) root.scale.setScalar(obj.transform.scale);
    tagWithId(root, obj.id);

    const bboxWorld = new THREE.Box3().setFromObject(root);

    return {
      id: obj.id,
      object3d: root,
      label: prettyLabel(obj.class),
      classification: obj.class,
      bboxWorld,
      meshOrigin: obj.source?.mesh_origin ?? "scene-json",
      physics: {
        isRigid: obj.physics.is_rigid,
        massKg: obj.physics.mass_kg,
        friction: obj.physics.friction,
        restitution: obj.physics.restitution,
      },
      legacySpec: obj,
    };
  }
}

export class SceneJsonFetchError extends Error {
  readonly status: number;
  readonly url: string;

  constructor(message: string, status: number, url: string) {
    super(message);
    this.name = "SceneJsonFetchError";
    this.status = status;
    this.url = url;
  }
}

export function validateSceneSpec(m: unknown, source: string): asserts m is SceneSpec {
  if (!m || typeof m !== "object") {
    throw new Error(`scene.json (${source}) is not an object`);
  }
  const mm = m as Partial<SceneSpec>;
  if (mm.version !== "1.0") {
    throw new Error(`scene.json (${source}) has unsupported version: ${String(mm.version)}`);
  }
  if (!Array.isArray(mm.objects)) {
    throw new Error(`scene.json (${source}) missing "objects" array`);
  }
  for (const [i, obj] of mm.objects.entries()) {
    if (!obj.id) throw new Error(`objects[${i}] missing id`);
    if (!obj.mesh) throw new Error(`objects[${i}] missing mesh`);
    if (!obj.transform?.translation || obj.transform.translation.length !== 3)
      throw new Error(`objects[${i}] invalid translation`);
    if (!obj.transform?.rotation_quat || obj.transform.rotation_quat.length !== 4)
      throw new Error(`objects[${i}] invalid rotation_quat`);
    if (!obj.physics) throw new Error(`objects[${i}] missing physics`);
  }
}

export function resolveBaseUrl(manifestUrl: string): string {
  try {
    return new URL(".", manifestUrl).toString();
  } catch {
    const origin =
      typeof window !== "undefined" && window.location
        ? window.location.origin
        : "http://localhost/";
    return new URL(".", new URL(manifestUrl, origin)).toString();
  }
}

function framingHint(meshes: LoadedMesh[], groundY: number): LoadedScene["cameraHint"] {
  if (meshes.length === 0) {
    return { position: [1.2, 0.8, 1.2], target: [0, 0.1, 0] };
  }
  const union = new THREE.Box3();
  for (const m of meshes) union.union(m.bboxWorld);
  const center = union.getCenter(new THREE.Vector3());
  const size = union.getSize(new THREE.Vector3());
  const diag = Math.max(size.length(), 0.2);
  const back = Math.max(diag * 2.5, 0.6);
  return {
    position: [center.x + back * 0.6, center.y + back * 0.9, center.z + back],
    target: [center.x, Math.max(center.y, groundY + 0.05), center.z],
  };
}

function deriveGroundY(meshes: LoadedMesh[], source: string): number {
  if (meshes.length === 0) return 0;
  let minY = Number.POSITIVE_INFINITY;
  for (const mesh of meshes) {
    minY = Math.min(minY, mesh.bboxWorld.min.y);
  }
  if (!Number.isFinite(minY)) return 0;
  if (minY >= -0.05) return 0;
  console.warn(
    "[SceneJsonSource] scene appears vertically offset; using bbox-derived groundY fallback",
    { source, derivedGroundY: minY },
  );
  return minY;
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
