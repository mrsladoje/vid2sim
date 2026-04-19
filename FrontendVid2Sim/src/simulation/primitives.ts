import * as THREE from "three";
import type { SceneObject } from "./types";

const MATERIAL_COLORS: Record<string, number> = {
  wood: 0x8b5a2b,
  rubber: 0xcc3333,
  ceramic: 0xeeeeee,
  paper: 0xd8c5a6,
  metal: 0x9aa0a6,
  plastic: 0x3b82f6,
  fabric: 0x6b7280,
  glass: 0xbfd7ea,
  unknown: 0x7f7f7f,
};

function matColor(material_class: string): number {
  return MATERIAL_COLORS[material_class] ?? MATERIAL_COLORS.unknown;
}

export function buildPrimitiveMesh(obj: SceneObject): THREE.Object3D {
  const color = matColor(obj.material_class);
  const material = new THREE.MeshStandardMaterial({
    color,
    roughness: 0.75,
    metalness: 0.05,
  });

  const scheme = obj.mesh.startsWith("primitive:") ? obj.mesh.slice(10) : "box";

  switch (scheme) {
    case "sphere": {
      const r = obj.collider.radius ?? 0.15;
      const g = new THREE.SphereGeometry(r, 32, 24);
      const m = new THREE.Mesh(g, material);
      m.castShadow = true;
      m.receiveShadow = true;
      return m;
    }
    case "cylinder": {
      const r = obj.collider.radius ?? 0.1;
      const h = obj.collider.height ?? 0.2;
      const g = new THREE.CylinderGeometry(r, r, h, 24);
      const m = new THREE.Mesh(g, material);
      m.castShadow = true;
      m.receiveShadow = true;
      return m;
    }
    case "capsule": {
      const r = obj.collider.radius ?? 0.1;
      const h = obj.collider.height ?? 0.3;
      const g = new THREE.CapsuleGeometry(r, h, 8, 16);
      const m = new THREE.Mesh(g, material);
      m.castShadow = true;
      m.receiveShadow = true;
      return m;
    }
    case "chair":
      return buildChair(material);
    case "table":
      return buildTable(material);
    case "box":
    default: {
      const he = obj.collider.half_extents ?? [0.25, 0.25, 0.25];
      const g = new THREE.BoxGeometry(he[0] * 2, he[1] * 2, he[2] * 2);
      const m = new THREE.Mesh(g, material);
      m.castShadow = true;
      m.receiveShadow = true;
      return m;
    }
  }
}

function buildChair(mat: THREE.MeshStandardMaterial): THREE.Object3D {
  const g = new THREE.Group();
  const seat = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.05, 0.45), mat);
  seat.castShadow = true;
  seat.receiveShadow = true;
  g.add(seat);

  const back = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.5, 0.04), mat);
  back.position.set(0, 0.275, -0.2);
  back.castShadow = true;
  g.add(back);

  const legGeo = new THREE.BoxGeometry(0.04, 0.45, 0.04);
  for (const [x, z] of [
    [0.2, 0.2],
    [-0.2, 0.2],
    [0.2, -0.2],
    [-0.2, -0.2],
  ]) {
    const leg = new THREE.Mesh(legGeo, mat);
    leg.position.set(x, -0.25, z);
    leg.castShadow = true;
    g.add(leg);
  }
  return g;
}

function buildTable(mat: THREE.MeshStandardMaterial): THREE.Object3D {
  const g = new THREE.Group();
  const top = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.05, 0.8), mat);
  top.position.y = 0.375;
  top.castShadow = true;
  top.receiveShadow = true;
  g.add(top);
  const legGeo = new THREE.BoxGeometry(0.06, 0.8, 0.06);
  for (const [x, z] of [
    [0.55, 0.35],
    [-0.55, 0.35],
    [0.55, -0.35],
    [-0.55, -0.35],
  ]) {
    const leg = new THREE.Mesh(legGeo, mat);
    leg.position.set(x, 0, z);
    leg.castShadow = true;
    g.add(leg);
  }
  return g;
}
