import { describe, it, expect, beforeAll } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import RAPIER from "@dimforge/rapier3d-compat";
import {
  validateSceneSpec,
  SceneValidationError,
} from "../../web/src/loader";

const projectRoot = resolve(__dirname, "..", "..");

function loadFixture(rel: string): unknown {
  return JSON.parse(readFileSync(resolve(projectRoot, rel), "utf-8"));
}

describe("scene schema validator", () => {
  it("accepts spec/scene.example.json", () => {
    const raw = loadFixture("spec/scene.example.json");
    const spec = validateSceneSpec(raw);
    expect(spec.version).toBe("1.0");
    expect(spec.objects.length).toBe(3);
    expect(spec.objects[0].id).toBe("chair_01");
  });

  it("accepts data/scenes/stub_01/scene.json", () => {
    const raw = loadFixture("data/scenes/stub_01/scene.json");
    const spec = validateSceneSpec(raw);
    expect(spec.objects.length).toBe(1);
  });

  it("accepts data/scenes/demo_scene/scene.json and caps at ≤8 objects", () => {
    const raw = loadFixture("data/scenes/demo_scene/scene.json");
    const spec = validateSceneSpec(raw);
    expect(spec.objects.length).toBeGreaterThanOrEqual(3);
    expect(spec.objects.length).toBeLessThanOrEqual(8);
  });

  it("rejects a bad version", () => {
    const bad = { ...(loadFixture("spec/scene.example.json") as object), version: "0.9" };
    expect(() => validateSceneSpec(bad)).toThrow(SceneValidationError);
  });

  it("rejects a missing required collider field", () => {
    const raw = loadFixture("spec/scene.example.json") as {
      objects: Array<Record<string, unknown>>;
    };
    const mutated = JSON.parse(JSON.stringify(raw));
    delete mutated.objects[0].collider;
    expect(() => validateSceneSpec(mutated)).toThrow(SceneValidationError);
  });

  it("rejects a scale ≤ 0", () => {
    const raw = JSON.parse(JSON.stringify(loadFixture("spec/scene.example.json")));
    raw.objects[0].transform.scale = 0;
    expect(() => validateSceneSpec(raw)).toThrow(SceneValidationError);
  });

  it("rejects more than 8 objects (NFR)", () => {
    const raw = JSON.parse(JSON.stringify(loadFixture("spec/scene.example.json")));
    const template = raw.objects[0];
    raw.objects = Array.from({ length: 9 }, (_, i) => ({
      ...template,
      id: `obj_${i}`,
    }));
    expect(() => validateSceneSpec(raw)).toThrow(/caps at 8/);
  });
});

describe("Rapier physics smoke", () => {
  beforeAll(async () => {
    await RAPIER.init();
  });

  it("simulates 1 s of gravity with the example scene's bodies and no errors", () => {
    const spec = validateSceneSpec(loadFixture("spec/scene.example.json"));
    const g = spec.world.gravity;
    const world = new RAPIER.World({ x: g[0], y: g[1], z: g[2] });

    // Ground.
    const groundBody = world.createRigidBody(RAPIER.RigidBodyDesc.fixed());
    world.createCollider(
      RAPIER.ColliderDesc.cuboid(50, 0.05, 50)
        .setTranslation(0, -0.05, 0)
        .setFriction(spec.ground.material.friction)
        .setRestitution(spec.ground.material.restitution),
      groundBody,
    );

    const bodies = [];
    for (const obj of spec.objects) {
      const t = obj.transform.translation;
      const body = world.createRigidBody(
        RAPIER.RigidBodyDesc.dynamic().setTranslation(t[0], t[1], t[2]),
      );
      const shape = obj.collider;
      let colDesc: RAPIER.ColliderDesc;
      if (shape.shape === "sphere") {
        colDesc = RAPIER.ColliderDesc.ball(shape.radius ?? 0.1);
      } else if (shape.shape === "cylinder") {
        colDesc = RAPIER.ColliderDesc.cylinder(
          (shape.height ?? 0.2) / 2,
          shape.radius ?? 0.1,
        );
      } else {
        const he = shape.half_extents ?? [0.25, 0.25, 0.25];
        colDesc = RAPIER.ColliderDesc.cuboid(he[0], he[1], he[2]);
      }
      colDesc.setFriction(obj.physics.friction).setRestitution(obj.physics.restitution);
      world.createCollider(colDesc, body);
      bodies.push({ body, id: obj.id });
    }

    // Step 60 times at 1/60s, equivalent to ~1 s of simulation.
    world.timestep = 1 / 60;
    for (let i = 0; i < 60; i++) world.step();

    expect(bodies.length).toBe(3);
    // Ball started at y=1.0, restitution 0.75 — after 1 s of physics it has
    // moved noticeably. The exact value depends on Rapier CCD + integrator
    // tolerances, so we just assert it's no longer at its start height.
    const ball = bodies.find((b) => b.id === "ball_01");
    expect(ball).toBeDefined();
    const ballY = ball!.body.translation().y;
    expect(ballY).not.toBeCloseTo(1.0, 3);
    // Nothing went NaN, which would indicate integrator blow-up.
    for (const b of bodies) {
      const p = b.body.translation();
      expect(Number.isFinite(p.x)).toBe(true);
      expect(Number.isFinite(p.y)).toBe(true);
      expect(Number.isFinite(p.z)).toBe(true);
    }
    world.free();
  });
});
