import { describe, it, expect } from "vitest";
import * as THREE from "three";
import { buildPrimitiveMesh } from "../../web/src/primitives";
import { makeSceneObject } from "./_harness";

describe("buildPrimitiveMesh", () => {
  it("builds a sphere with explicit radius", () => {
    const obj = makeSceneObject({
      mesh: "primitive:sphere",
      collider: { shape: "sphere", radius: 0.3 },
    });
    const mesh = buildPrimitiveMesh(obj) as THREE.Mesh;
    expect(mesh).toBeInstanceOf(THREE.Mesh);
    expect(mesh.geometry).toBeInstanceOf(THREE.SphereGeometry);
    // SphereGeometry stores the radius on its .parameters.
    expect((mesh.geometry as THREE.SphereGeometry).parameters.radius).toBeCloseTo(0.3);
    expect(mesh.castShadow).toBe(true);
  });

  it("builds a cylinder with the given half-height convention", () => {
    const obj = makeSceneObject({
      mesh: "primitive:cylinder",
      collider: { shape: "cylinder", radius: 0.1, height: 0.4 },
    });
    const mesh = buildPrimitiveMesh(obj) as THREE.Mesh;
    expect(mesh.geometry).toBeInstanceOf(THREE.CylinderGeometry);
  });

  it("builds a box using half_extents ×2 for full BoxGeometry dims", () => {
    const obj = makeSceneObject({
      mesh: "primitive:box",
      collider: { shape: "box", half_extents: [0.3, 0.4, 0.5] },
    });
    const mesh = buildPrimitiveMesh(obj) as THREE.Mesh;
    const geo = mesh.geometry as THREE.BoxGeometry;
    expect(geo.parameters.width).toBeCloseTo(0.6);
    expect(geo.parameters.height).toBeCloseTo(0.8);
    expect(geo.parameters.depth).toBeCloseTo(1.0);
  });

  it("colours meshes from material_class (wood vs rubber differ)", () => {
    const wood = buildPrimitiveMesh(
      makeSceneObject({ material_class: "wood", mesh: "primitive:box" }),
    ) as THREE.Mesh;
    const rubber = buildPrimitiveMesh(
      makeSceneObject({ material_class: "rubber", mesh: "primitive:box" }),
    ) as THREE.Mesh;
    const cWood = (wood.material as THREE.MeshStandardMaterial).color.getHex();
    const cRubber = (rubber.material as THREE.MeshStandardMaterial).color.getHex();
    expect(cWood).not.toBe(cRubber);
    // Unknown class falls back to the shared 'unknown' grey.
    const unknown = buildPrimitiveMesh(
      makeSceneObject({ material_class: "not-a-real-material", mesh: "primitive:box" }),
    ) as THREE.Mesh;
    expect((unknown.material as THREE.MeshStandardMaterial).color.getHex()).toBe(0x7f7f7f);
  });

  it("builds a chair group with seat, back, and 4 legs (6 meshes)", () => {
    const obj = makeSceneObject({ mesh: "primitive:chair", class: "chair", material_class: "wood" });
    const group = buildPrimitiveMesh(obj) as THREE.Group;
    expect(group).toBeInstanceOf(THREE.Group);
    // 1 seat + 1 back + 4 legs = 6 children.
    expect(group.children.length).toBe(6);
    expect(group.children.every((c) => (c as THREE.Mesh).isMesh)).toBe(true);
  });

  it("builds a table group with top + 4 legs (5 meshes)", () => {
    const obj = makeSceneObject({ mesh: "primitive:table", class: "table", material_class: "wood" });
    const group = buildPrimitiveMesh(obj) as THREE.Group;
    expect(group.children.length).toBe(5);
  });

  it("falls back to box geometry when the scheme is unknown", () => {
    const obj = makeSceneObject({
      mesh: "primitive:blimp",
      collider: { shape: "box", half_extents: [0.1, 0.1, 0.1] },
    });
    const mesh = buildPrimitiveMesh(obj) as THREE.Mesh;
    expect(mesh.geometry).toBeInstanceOf(THREE.BoxGeometry);
  });
});
