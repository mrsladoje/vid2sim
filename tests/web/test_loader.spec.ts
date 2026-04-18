import { describe, it, expect, vi, beforeEach } from "vitest";
import { loadScene, SceneValidationError, validateSceneSpec } from "../../web/src/loader";

// Schema-shaped fixture used by a couple of tests below.
const EXAMPLE = {
  version: "1.0",
  world: { gravity: [0, -9.81, 0], up_axis: "y", unit: "meters" },
  ground: { type: "plane", normal: [0, 1, 0], material: { friction: 0.8, restitution: 0.1 } },
  objects: [
    {
      id: "chair_01",
      class: "chair",
      mesh: "primitive:chair",
      transform: { translation: [0, 0.5, 0], rotation_quat: [0, 0, 0, 1], scale: 1 },
      collider: { shape: "box", half_extents: [0.25, 0.25, 0.25] },
      physics: { mass_kg: 1, friction: 0.5, restitution: 0.3, is_rigid: true },
      material_class: "wood",
      source: { mesh_origin: "primitive", physics_origin: "lookup", vlm_reasoning: "—" },
    },
  ],
};

describe("loadScene (HTTP fetch path)", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("returns a validated SceneSpec when the server responds 200 with valid JSON", async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(EXAMPLE), { status: 200 })) as typeof fetch;
    const spec = await loadScene("/scene.json");
    expect(spec.version).toBe("1.0");
    expect(spec.objects[0].id).toBe("chair_01");
  });

  it("throws a plain Error (not SceneValidationError) on HTTP failure", async () => {
    globalThis.fetch = vi.fn(async () => new Response("nope", { status: 404 })) as typeof fetch;
    await expect(loadScene("/missing.json")).rejects.toThrow(/HTTP 404/);
  });

  it("throws SceneValidationError when the server returns schema-invalid JSON", async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ version: "0.9" }), { status: 200 })) as typeof fetch;
    await expect(loadScene("/bad.json")).rejects.toBeInstanceOf(SceneValidationError);
  });
});

describe("validateSceneSpec — extra rejection cases", () => {
  it("rejects a collider with an unknown shape", () => {
    const bad = JSON.parse(JSON.stringify(EXAMPLE));
    bad.objects[0].collider.shape = "doughnut";
    expect(() => validateSceneSpec(bad)).toThrow(/invalid shape/);
  });

  it("rejects a non-finite number in a vec3", () => {
    const bad = JSON.parse(JSON.stringify(EXAMPLE));
    bad.world.gravity = [0, NaN, 0];
    expect(() => validateSceneSpec(bad)).toThrow(SceneValidationError);
  });

  it("rejects an unknown physics_origin", () => {
    const bad = JSON.parse(JSON.stringify(EXAMPLE));
    bad.objects[0].source.physics_origin = "ouija";
    expect(() => validateSceneSpec(bad)).toThrow(/unknown physics_origin/);
  });

  it("rejects an up_axis other than 'y' or 'z'", () => {
    const bad = JSON.parse(JSON.stringify(EXAMPLE));
    bad.world.up_axis = "x";
    expect(() => validateSceneSpec(bad)).toThrow(/up_axis/);
  });

  it("accepts optional camera_pose when present and well-formed", () => {
    const ok = JSON.parse(JSON.stringify(EXAMPLE));
    ok.camera_pose = { translation: [2, 1.5, 2], rotation_quat: [0, 0, 0, 1] };
    const spec = validateSceneSpec(ok);
    expect(spec.camera_pose?.translation[0]).toBe(2);
  });

  it("rejects a non-object root", () => {
    expect(() => validateSceneSpec("nope" as unknown)).toThrow(/expected JSON object/);
  });
});
