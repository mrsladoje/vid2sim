import * as THREE from "three";
import type { Viewer, ObjectRecord } from "../../web/src/viewer";
import type { Physics } from "../../web/src/physics";
import { SceneObject, SceneSpec } from "../../web/src/types/scene";
import { buildPrimitiveMesh } from "../../web/src/primitives";

// Mount a copy of index.html's sidebar DOM that UI.ts expects. The list here
// is intentionally identical to the `requireEl` IDs referenced in ui.ts; if
// UI gains a new element, the test will fail loud at construction.
export function mountSidebarDom(): void {
  document.body.innerHTML = `
    <canvas id="viewer" width="800" height="600"></canvas>
    <button id="btn-reset"></button>
    <button id="btn-load-example"></button>
    <button id="btn-load-stub"></button>
    <button id="btn-load-demo"></button>
    <label><input type="radio" name="mode" value="select" checked /></label>
    <label><input type="radio" name="mode" value="drag" /></label>
    <label><input type="radio" name="mode" value="drop_ball" /></label>
    <label><input type="radio" name="mode" value="apply_force" /></label>
    <span id="mode-label"></span>
    <span id="fps"></span>
    <span id="body-count"></span>
    <div id="info-empty" style="display:block"></div>
    <div id="info-populated" style="display:none"></div>
    <span id="info-id"></span>
    <span id="info-class"></span>
    <span id="info-mass"></span>
    <span id="info-friction"></span>
    <span id="info-restitution"></span>
    <span id="info-material"></span>
    <span id="info-mesh-origin"></span>
    <span id="info-physics-origin"></span>
    <span id="info-reasoning"></span>
  `;
}

export function getCanvas(): HTMLCanvasElement {
  const c = document.getElementById("viewer") as HTMLCanvasElement | null;
  if (!c) throw new Error("test DOM missing #viewer — call mountSidebarDom() first");
  // jsdom implements getBoundingClientRect but returns 0 by default. Pretend
  // the canvas is 800×600 at the origin so NDC math is sane.
  c.getBoundingClientRect = () =>
    ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
  return c;
}

// A stand-in Viewer. It holds a real THREE.Scene (Physics needs it) and a
// real PerspectiveCamera (UI reads camera matrix for apply_force impulses),
// but it avoids constructing a WebGLRenderer which jsdom cannot back.
export interface MockViewer {
  readonly scene: THREE.Scene;
  readonly camera: THREE.PerspectiveCamera;
  readonly canvas: HTMLCanvasElement;
  readonly objects: Map<string, ObjectRecord>;
  highlightCalls: (string | null)[];
  pickResponses: (ObjectRecord | null)[];
  planeIntersectResponses: (THREE.Vector3 | null)[];
  pick(clientX: number, clientY: number): ObjectRecord | null;
  planeIntersect(clientX: number, clientY: number, h: number): THREE.Vector3 | null;
  setHighlight(id: string | null): void;
  clearHighlight(): void;
  ndcFromPixel(x: number, y: number, out: THREE.Vector2): THREE.Vector2;
  render(): void;
  resize(): void;
  loadSpec(spec: SceneSpec, baseUrl?: string): Promise<void>;
}

export function makeMockViewer(canvas = getCanvas()): MockViewer & Viewer {
  const mv: MockViewer = {
    scene: new THREE.Scene(),
    camera: new THREE.PerspectiveCamera(55, 800 / 600, 0.05, 200),
    canvas,
    objects: new Map(),
    highlightCalls: [],
    pickResponses: [],
    planeIntersectResponses: [],
    pick(_x, _y) {
      return mv.pickResponses.length ? mv.pickResponses.shift()! : null;
    },
    planeIntersect(_x, _y, _h) {
      return mv.planeIntersectResponses.length
        ? mv.planeIntersectResponses.shift()!
        : null;
    },
    setHighlight(id) {
      mv.highlightCalls.push(id);
    },
    clearHighlight() {
      mv.highlightCalls.push(null);
    },
    ndcFromPixel(x, y, out) {
      out.set((x / 800) * 2 - 1, -(y / 600) * 2 + 1);
      return out;
    },
    render() {},
    resize() {},
    async loadSpec(spec, _baseUrl) {
      for (const obj of spec.objects) {
        const mesh = buildPrimitiveMesh({
          ...obj,
          mesh: obj.mesh.startsWith("primitive:") ? obj.mesh : `primitive:${obj.collider.shape}`,
        });
        mesh.userData.objectId = obj.id;
        mesh.traverse((c) => {
          c.userData.objectId = obj.id;
        });
        const t = obj.transform.translation;
        mesh.position.set(t[0], t[1], t[2]);
        mv.scene.add(mesh);
        mv.objects.set(obj.id, { id: obj.id, spec: obj, mesh, bodyHandle: null });
      }
    },
  };
  mv.camera.position.set(3, 2.2, 3.5);
  mv.camera.lookAt(0, 0.4, 0);
  return mv as MockViewer & Viewer;
}

// Seed the mock viewer's object map directly from plain spec objects — useful
// for UI tests that don't care about mesh geometry.
export function seedObjects(viewer: MockViewer, specs: SceneObject[]): void {
  for (const obj of specs) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.1));
    mesh.userData.objectId = obj.id;
    viewer.scene.add(mesh);
    viewer.objects.set(obj.id, { id: obj.id, spec: obj, mesh, bodyHandle: null });
  }
}

export function minimalSpec(objects: SceneObject[] = []): SceneSpec {
  return {
    version: "1.0",
    world: { gravity: [0, -9.81, 0], up_axis: "y", unit: "meters" },
    ground: { type: "plane", normal: [0, 1, 0], material: { friction: 0.8, restitution: 0.1 } },
    objects,
  };
}

export function makeSceneObject(overrides: Partial<SceneObject> = {}): SceneObject {
  return {
    id: overrides.id ?? "obj_1",
    class: overrides.class ?? "box",
    mesh: overrides.mesh ?? "primitive:box",
    transform: overrides.transform ?? {
      translation: [0, 0.5, 0],
      rotation_quat: [0, 0, 0, 1],
      scale: 1,
    },
    collider: overrides.collider ?? { shape: "box", half_extents: [0.25, 0.25, 0.25] },
    physics: overrides.physics ?? {
      mass_kg: 1,
      friction: 0.5,
      restitution: 0.3,
      is_rigid: true,
    },
    material_class: overrides.material_class ?? "wood",
    source: overrides.source,
  };
}

// Shape of Physics used by UI. We pass a real Physics object whenever the test
// cares about simulation; otherwise a recorder is enough.
export interface PhysicsRecorder {
  dropBallCalls: THREE.Vector3[];
  applyImpulseCalls: { id: string; impulse: THREE.Vector3 }[];
  resetCalls: number;
  bodies: Map<string, unknown>;
}

export function makeMockPhysics(): PhysicsRecorder & Physics {
  // Note: recorder state lives on `fake` itself so that the test keeps a live
  // reference to the same counters the methods mutate. Spreading `rec` would
  // copy primitive fields by value and silently fork the counts.
  const fake: PhysicsRecorder & {
    dropBall(p: THREE.Vector3): void;
    applyImpulse(id: string, impulse: THREE.Vector3): void;
    reset(): void;
    getBodyFor(id: string): unknown;
    bodyCount(): number;
  } = {
    dropBallCalls: [],
    applyImpulseCalls: [],
    resetCalls: 0,
    bodies: new Map(),
    dropBall(pos) {
      fake.dropBallCalls.push(pos.clone());
    },
    applyImpulse(id, impulse) {
      fake.applyImpulseCalls.push({ id, impulse: impulse.clone() });
    },
    reset() {
      fake.resetCalls += 1;
    },
    getBodyFor(id) {
      return fake.bodies.get(id);
    },
    bodyCount() {
      return fake.bodies.size;
    },
  };
  return fake as unknown as PhysicsRecorder & Physics;
}
