/** @vitest-environment jsdom */
import { describe, it, expect, beforeAll } from "vitest";
import RAPIER from "@dimforge/rapier3d-compat";
import * as THREE from "three";
import { Physics } from "../../web/src/physics";
import {
  makeMockViewer,
  makeSceneObject,
  minimalSpec,
  mountSidebarDom,
} from "./_harness";

beforeAll(async () => {
  await RAPIER.init();
});

function newViewerWithObjects(ids: string[]) {
  mountSidebarDom();
  const viewer = makeMockViewer();
  const spec = minimalSpec(
    ids.map((id, idx) =>
      makeSceneObject({
        id,
        transform: { translation: [idx * 1.2, 0.5, 0], rotation_quat: [0, 0, 0, 1], scale: 1 },
        collider:
          idx === 0
            ? { shape: "sphere", radius: 0.15 }
            : { shape: "box", half_extents: [0.2, 0.2, 0.2] },
      }),
    ),
  );
  // Seed viewer.objects with primitive meshes so Physics can wire them.
  return { viewer, spec };
}

describe("Physics lifecycle", () => {
  it("init is idempotent and safe to call twice", async () => {
    const { viewer } = newViewerWithObjects([]);
    const phys = new Physics(viewer);
    await phys.init();
    await expect(phys.init()).resolves.toBeUndefined();
  });

  it("buildWorld wires one body per spec object (ground excluded from bodyCount)", async () => {
    const { viewer, spec } = newViewerWithObjects(["a", "b", "c"]);
    const phys = new Physics(viewer);
    await phys.init();
    await viewer.loadSpec(spec);
    phys.buildWorld(spec);
    expect(phys.bodyCount()).toBe(3);
    expect(phys.getBodyFor("a")).toBeDefined();
    expect(phys.getBodyFor("missing")).toBeUndefined();
  });

  it("step advances simulation — a ball above the ground falls", async () => {
    const { viewer, spec } = newViewerWithObjects(["ball"]);
    const phys = new Physics(viewer);
    await phys.init();
    await viewer.loadSpec(spec);
    // Put the ball at y=2 so it has room to fall.
    spec.objects[0].transform.translation = [0, 2.0, 0];
    phys.buildWorld(spec);
    const ball = phys.getBodyFor("ball")!;
    const y0 = ball.translation().y;
    for (let i = 0; i < 30; i++) phys.step(1 / 60);
    expect(ball.translation().y).toBeLessThan(y0);
  });

  it("dropBall appends an extra body and a mesh", async () => {
    const { viewer, spec } = newViewerWithObjects([]);
    const phys = new Physics(viewer);
    await phys.init();
    phys.buildWorld(spec);
    const before = phys.bodyCount();
    phys.dropBall(new THREE.Vector3(0, 1.5, 0));
    expect(phys.bodyCount()).toBe(before + 1);
    // The ball mesh was added to the viewer scene.
    const meshCount = viewer.scene.children.filter((c) => (c as THREE.Mesh).isMesh).length;
    expect(meshCount).toBeGreaterThan(0);
  });

  it("applyImpulse moves the targeted body in one simulation step", async () => {
    const { viewer, spec } = newViewerWithObjects(["target"]);
    const phys = new Physics(viewer);
    await phys.init();
    await viewer.loadSpec(spec);
    phys.buildWorld(spec);
    const body = phys.getBodyFor("target")!;
    const x0 = body.translation().x;
    phys.applyImpulse("target", new THREE.Vector3(5, 0, 0));
    phys.step(1 / 60);
    expect(body.translation().x).toBeGreaterThan(x0);
  });

  it("reset rebuilds the world from the last spec (bodies reset to start)", async () => {
    const { viewer, spec } = newViewerWithObjects(["target"]);
    spec.objects[0].transform.translation = [0, 3.0, 0];
    const phys = new Physics(viewer);
    await phys.init();
    await viewer.loadSpec(spec);
    phys.buildWorld(spec);
    // Simulate for a bit so body moves.
    for (let i = 0; i < 20; i++) phys.step(1 / 60);
    const movedY = phys.getBodyFor("target")!.translation().y;
    expect(movedY).toBeLessThan(3.0);
    phys.reset();
    // After reset, a fresh body exists with the original translation.
    expect(phys.getBodyFor("target")!.translation().y).toBeCloseTo(3.0, 5);
  });

  it("teardown removes all bodies and clears bodyHandle on viewer records", async () => {
    const { viewer, spec } = newViewerWithObjects(["x"]);
    const phys = new Physics(viewer);
    await phys.init();
    await viewer.loadSpec(spec);
    phys.buildWorld(spec);
    expect(viewer.objects.get("x")?.bodyHandle).toBeGreaterThanOrEqual(0);
    phys.teardown();
    expect(phys.bodyCount()).toBe(0);
    expect(viewer.objects.get("x")?.bodyHandle).toBeNull();
  });

  it("step does nothing before buildWorld (no crash)", () => {
    mountSidebarDom();
    const viewer = makeMockViewer();
    const phys = new Physics(viewer);
    expect(() => phys.step(1 / 60)).not.toThrow();
    expect(phys.bodyCount()).toBe(0);
  });

  it("ball extras expire after their TTL", async () => {
    const { viewer, spec } = newViewerWithObjects([]);
    const phys = new Physics(viewer);
    await phys.init();
    phys.buildWorld(spec);
    phys.dropBall(new THREE.Vector3(0, 1.5, 0));
    expect(phys.bodyCount()).toBe(1);
    // Advance in small chunks well past the 12 s TTL.
    for (let i = 0; i < 40; i++) phys.step(0.4);
    expect(phys.bodyCount()).toBe(0);
  });
});
