import {
  SceneSpec,
  SceneObject,
  Vec3,
  Quat,
  ColliderShape,
} from "./types/scene";

export class SceneValidationError extends Error {
  constructor(message: string, public readonly path: string) {
    super(`SceneSpec invalid at ${path}: ${message}`);
    this.name = "SceneValidationError";
  }
}

function isFiniteNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

function checkVec3(v: unknown, path: string): Vec3 {
  if (!Array.isArray(v) || v.length !== 3 || !v.every(isFiniteNumber)) {
    throw new SceneValidationError("expected [number, number, number]", path);
  }
  return v as Vec3;
}

function checkQuat(v: unknown, path: string): Quat {
  if (!Array.isArray(v) || v.length !== 4 || !v.every(isFiniteNumber)) {
    throw new SceneValidationError("expected quaternion [x, y, z, w]", path);
  }
  return v as Quat;
}

function checkStr(v: unknown, path: string): string {
  if (typeof v !== "string" || v.length === 0) {
    throw new SceneValidationError("expected non-empty string", path);
  }
  return v;
}

function checkNum(v: unknown, path: string): number {
  if (!isFiniteNumber(v)) {
    throw new SceneValidationError("expected finite number", path);
  }
  return v;
}

function checkBool(v: unknown, path: string): boolean {
  if (typeof v !== "boolean") {
    throw new SceneValidationError("expected boolean", path);
  }
  return v;
}

const VALID_SHAPES: ReadonlySet<ColliderShape> = new Set([
  "mesh",
  "box",
  "sphere",
  "cylinder",
  "capsule",
]);

function validateObject(raw: unknown, idx: number): SceneObject {
  const path = `objects[${idx}]`;
  if (typeof raw !== "object" || raw === null) {
    throw new SceneValidationError("expected object", path);
  }
  const o = raw as Record<string, unknown>;

  const id = checkStr(o.id, `${path}.id`);
  const cls = checkStr(o.class, `${path}.class`);
  const mesh = checkStr(o.mesh, `${path}.mesh`);
  const material_class = checkStr(o.material_class, `${path}.material_class`);

  const t = o.transform as Record<string, unknown> | undefined;
  if (!t) throw new SceneValidationError("missing transform", path);
  const transform = {
    translation: checkVec3(t.translation, `${path}.transform.translation`),
    rotation_quat: checkQuat(t.rotation_quat, `${path}.transform.rotation_quat`),
    scale: checkNum(t.scale, `${path}.transform.scale`),
  };
  if (transform.scale <= 0) {
    throw new SceneValidationError("scale must be > 0", `${path}.transform.scale`);
  }

  const c = o.collider as Record<string, unknown> | undefined;
  if (!c) throw new SceneValidationError("missing collider", path);
  const shape = checkStr(c.shape, `${path}.collider.shape`) as ColliderShape;
  if (!VALID_SHAPES.has(shape)) {
    throw new SceneValidationError(`invalid shape "${shape}"`, `${path}.collider.shape`);
  }
  const collider: SceneObject["collider"] = { shape };
  if (c.convex_decomposition !== undefined) {
    collider.convex_decomposition = checkBool(
      c.convex_decomposition,
      `${path}.collider.convex_decomposition`,
    );
  }
  if (c.half_extents !== undefined) {
    collider.half_extents = checkVec3(c.half_extents, `${path}.collider.half_extents`);
  }
  if (c.radius !== undefined) {
    collider.radius = checkNum(c.radius, `${path}.collider.radius`);
  }
  if (c.height !== undefined) {
    collider.height = checkNum(c.height, `${path}.collider.height`);
  }

  const p = o.physics as Record<string, unknown> | undefined;
  if (!p) throw new SceneValidationError("missing physics", path);
  const physics = {
    mass_kg: checkNum(p.mass_kg, `${path}.physics.mass_kg`),
    friction: checkNum(p.friction, `${path}.physics.friction`),
    restitution: checkNum(p.restitution, `${path}.physics.restitution`),
    is_rigid: checkBool(p.is_rigid, `${path}.physics.is_rigid`),
  };

  const out: SceneObject = {
    id,
    class: cls,
    mesh,
    transform,
    collider,
    physics,
    material_class,
  };

  if (o.source !== undefined) {
    const s = o.source as Record<string, unknown>;
    out.source = {};
    if (s.mesh_origin !== undefined) {
      out.source.mesh_origin = checkStr(s.mesh_origin, `${path}.source.mesh_origin`);
    }
    if (s.physics_origin !== undefined) {
      const v = checkStr(s.physics_origin, `${path}.source.physics_origin`);
      if (v !== "vlm" && v !== "lookup" && v !== "manual") {
        throw new SceneValidationError(
          `unknown physics_origin "${v}"`,
          `${path}.source.physics_origin`,
        );
      }
      out.source.physics_origin = v;
    }
    if (s.vlm_reasoning !== undefined) {
      out.source.vlm_reasoning = checkStr(s.vlm_reasoning, `${path}.source.vlm_reasoning`);
    }
  }

  return out;
}

/** Validate a parsed JSON blob against the v1.0 schema, returning a typed SceneSpec or throwing. */
export function validateSceneSpec(raw: unknown): SceneSpec {
  if (typeof raw !== "object" || raw === null) {
    throw new SceneValidationError("expected JSON object", "$");
  }
  const r = raw as Record<string, unknown>;

  if (r.version !== "1.0") {
    throw new SceneValidationError(
      `expected version "1.0", got ${JSON.stringify(r.version)}`,
      "$.version",
    );
  }

  const w = r.world as Record<string, unknown> | undefined;
  if (!w) throw new SceneValidationError("missing world", "$");
  const world = {
    gravity: checkVec3(w.gravity, "$.world.gravity"),
    up_axis: checkStr(w.up_axis, "$.world.up_axis") as "y" | "z",
    unit: checkStr(w.unit, "$.world.unit") as "meters",
  };
  if (world.up_axis !== "y" && world.up_axis !== "z") {
    throw new SceneValidationError("up_axis must be 'y' or 'z'", "$.world.up_axis");
  }
  if (world.unit !== "meters") {
    throw new SceneValidationError("unit must be 'meters'", "$.world.unit");
  }

  const g = r.ground as Record<string, unknown> | undefined;
  if (!g) throw new SceneValidationError("missing ground", "$");
  if (g.type !== "plane") {
    throw new SceneValidationError("only 'plane' ground supported", "$.ground.type");
  }
  const gmat = g.material as Record<string, unknown> | undefined;
  if (!gmat) throw new SceneValidationError("missing ground.material", "$");
  const ground = {
    type: "plane" as const,
    normal: checkVec3(g.normal, "$.ground.normal"),
    material: {
      friction: checkNum(gmat.friction, "$.ground.material.friction"),
      restitution: checkNum(gmat.restitution, "$.ground.material.restitution"),
    },
  };

  if (!Array.isArray(r.objects)) {
    throw new SceneValidationError("missing or non-array 'objects'", "$.objects");
  }
  if (r.objects.length > 8) {
    throw new SceneValidationError(
      `scene has ${r.objects.length} objects; NFR caps at 8`,
      "$.objects",
    );
  }
  const objects = r.objects.map(validateObject);

  const spec: SceneSpec = {
    version: "1.0",
    world,
    ground,
    objects,
  };

  if (r.camera_pose !== undefined) {
    const cp = r.camera_pose as Record<string, unknown>;
    spec.camera_pose = {
      translation: checkVec3(cp.translation, "$.camera_pose.translation"),
      rotation_quat: checkQuat(cp.rotation_quat, "$.camera_pose.rotation_quat"),
    };
  }

  return spec;
}

/** Fetch a scene.json from a URL and validate it. Fail-loud on the first error. */
export async function loadScene(url: string): Promise<SceneSpec> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`failed to fetch ${url}: HTTP ${res.status}`);
  }
  const raw = await res.json();
  return validateSceneSpec(raw);
}
