import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { SceneSpec, SceneObject } from "./types";
import { buildPrimitiveMesh } from "./primitives";

export interface ObjectRecord {
  id: string;
  spec: SceneObject;
  mesh: THREE.Object3D;
  bodyHandle: number | null;
}

const BG_COLOR = 0x0a0a0c;
const FOG_NEAR = 14;
const FOG_FAR = 48;

export class Viewer {
  readonly scene: THREE.Scene;
  readonly camera: THREE.PerspectiveCamera;
  readonly renderer: THREE.WebGLRenderer;
  readonly canvas: HTMLCanvasElement;
  readonly objects: Map<string, ObjectRecord> = new Map();
  readonly ground: THREE.Mesh;

  private highlightTarget: THREE.Object3D | null = null;
  private readonly selectionMaterial: THREE.MeshStandardMaterial;
  private readonly originalMaterials: Map<THREE.Mesh, THREE.Material | THREE.Material[]> =
    new Map();
  private readonly resizeHandler: () => void;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(BG_COLOR);
    this.scene.fog = new THREE.Fog(BG_COLOR, FOG_NEAR, FOG_FAR);

    this.camera = new THREE.PerspectiveCamera(
      55,
      Math.max(canvas.clientWidth, 1) / Math.max(canvas.clientHeight, 1),
      0.05,
      200,
    );
    this.camera.position.set(3.0, 2.2, 3.5);
    this.camera.lookAt(0, 0.4, 0);

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(
      Math.max(canvas.clientWidth, 1),
      Math.max(canvas.clientHeight, 1),
      false,
    );
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;

    const hemi = new THREE.HemisphereLight(0xffd9c2, 0x1a1118, 0.45);
    this.scene.add(hemi);

    const sun = new THREE.DirectionalLight(0xffe4cf, 2.1);
    sun.position.set(4, 8, 4);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -6;
    sun.shadow.camera.right = 6;
    sun.shadow.camera.top = 6;
    sun.shadow.camera.bottom = -6;
    sun.shadow.camera.near = 0.5;
    sun.shadow.camera.far = 25;
    sun.shadow.bias = -0.0005;
    this.scene.add(sun);

    // A soft orange rim-light to tie the scene into the Vid2Sim palette.
    const rim = new THREE.DirectionalLight(0xe46b45, 0.35);
    rim.position.set(-5, 3, -4);
    this.scene.add(rim);

    const groundGeo = new THREE.PlaneGeometry(30, 30);
    const groundMat = new THREE.MeshStandardMaterial({
      color: 0x14141a,
      roughness: 0.95,
      metalness: 0.0,
    });
    this.ground = new THREE.Mesh(groundGeo, groundMat);
    this.ground.rotation.x = -Math.PI / 2;
    this.ground.receiveShadow = true;
    this.scene.add(this.ground);

    const gridHelper = new THREE.GridHelper(20, 40, 0xe46b45, 0x1e1e24);
    (gridHelper.material as THREE.Material).transparent = true;
    (gridHelper.material as THREE.Material).opacity = 0.25;
    gridHelper.position.y = 0.001;
    this.scene.add(gridHelper);

    this.selectionMaterial = new THREE.MeshStandardMaterial({
      color: 0xe46b45,
      emissive: 0x6b2410,
      roughness: 0.35,
      metalness: 0.2,
    });

    this.resizeHandler = () => this.resize();
    window.addEventListener("resize", this.resizeHandler);
  }

  resize(): void {
    const w = Math.max(this.canvas.clientWidth, 1);
    const h = Math.max(this.canvas.clientHeight, 1);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  }

  async loadSpec(spec: SceneSpec, baseUrl = ""): Promise<void> {
    this.clear();
    if (spec.camera_pose) {
      const t = spec.camera_pose.translation;
      this.camera.position.set(t[0], t[1], t[2]);
      this.camera.lookAt(0, 0.4, 0);
    }
    for (const obj of spec.objects) {
      const mesh = await this.buildMeshFor(obj, baseUrl);
      const t = obj.transform.translation;
      const q = obj.transform.rotation_quat;
      mesh.position.set(t[0], t[1], t[2]);
      mesh.quaternion.set(q[0], q[1], q[2], q[3]);
      if (obj.transform.scale !== 1.0) mesh.scale.setScalar(obj.transform.scale);
      mesh.userData.objectId = obj.id;
      mesh.traverse((c) => {
        c.userData.objectId = obj.id;
      });
      this.scene.add(mesh);
      this.objects.set(obj.id, { id: obj.id, spec: obj, mesh, bodyHandle: null });
    }
  }

  private async buildMeshFor(obj: SceneObject, baseUrl: string): Promise<THREE.Object3D> {
    if (obj.mesh.startsWith("primitive:")) return buildPrimitiveMesh(obj);
    const url = baseUrl ? new URL(obj.mesh, baseUrl).toString() : obj.mesh;
    try {
      const loader = new GLTFLoader();
      const gltf = await loader.loadAsync(url);
      const root = gltf.scene ?? gltf.scenes?.[0];
      if (!root) throw new Error(`glTF at ${url} has no scene`);
      root.traverse((c) => {
        if ((c as THREE.Mesh).isMesh) {
          (c as THREE.Mesh).castShadow = true;
          (c as THREE.Mesh).receiveShadow = true;
        }
      });
      return root;
    } catch (e) {
      console.warn(`mesh ${url} failed to load; falling back to primitive`, e);
      return buildPrimitiveMesh({ ...obj, mesh: `primitive:${obj.collider.shape}` });
    }
  }

  clear(): void {
    for (const rec of this.objects.values()) {
      this.scene.remove(rec.mesh);
      disposeRecursive(rec.mesh);
    }
    this.objects.clear();
    this.clearHighlight();
  }

  setHighlight(id: string | null): void {
    this.clearHighlight();
    if (id === null) return;
    const rec = this.objects.get(id);
    if (!rec) return;
    this.highlightTarget = rec.mesh;
    rec.mesh.traverse((c) => {
      if ((c as THREE.Mesh).isMesh) {
        const mesh = c as THREE.Mesh;
        this.originalMaterials.set(mesh, mesh.material);
        mesh.material = this.selectionMaterial;
      }
    });
  }

  clearHighlight(): void {
    if (!this.highlightTarget) return;
    this.highlightTarget.traverse((c) => {
      if ((c as THREE.Mesh).isMesh) {
        const mesh = c as THREE.Mesh;
        const orig = this.originalMaterials.get(mesh);
        if (orig) mesh.material = orig;
      }
    });
    this.originalMaterials.clear();
    this.highlightTarget = null;
  }

  render(): void {
    this.renderer.render(this.scene, this.camera);
  }

  ndcFromPixel(x: number, y: number, out: THREE.Vector2): THREE.Vector2 {
    const rect = this.canvas.getBoundingClientRect();
    out.x = ((x - rect.left) / rect.width) * 2 - 1;
    out.y = -((y - rect.top) / rect.height) * 2 + 1;
    return out;
  }

  pick(clientX: number, clientY: number): ObjectRecord | null {
    const ndc = new THREE.Vector2();
    this.ndcFromPixel(clientX, clientY, ndc);
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(ndc, this.camera);
    const meshes: THREE.Object3D[] = [];
    for (const rec of this.objects.values()) meshes.push(rec.mesh);
    const hits = raycaster.intersectObjects(meshes, true);
    if (hits.length === 0) return null;
    const id = hits[0].object.userData.objectId as string | undefined;
    if (!id) return null;
    return this.objects.get(id) ?? null;
  }

  planeIntersect(clientX: number, clientY: number, height: number): THREE.Vector3 | null {
    const ndc = new THREE.Vector2();
    this.ndcFromPixel(clientX, clientY, ndc);
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(ndc, this.camera);
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -height);
    const hit = new THREE.Vector3();
    if (raycaster.ray.intersectPlane(plane, hit)) return hit;
    return null;
  }

  dispose(): void {
    window.removeEventListener("resize", this.resizeHandler);
    this.clear();
    this.renderer.dispose();
  }
}

function disposeRecursive(obj: THREE.Object3D): void {
  obj.traverse((c) => {
    const mesh = c as THREE.Mesh;
    if (mesh.isMesh) {
      mesh.geometry?.dispose();
      const mat = mesh.material;
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else mat?.dispose();
    }
  });
}
