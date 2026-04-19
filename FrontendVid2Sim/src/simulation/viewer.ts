import * as THREE from "three";
import type { LoadedMesh, LoadedScene } from "./types";

export interface ObjectRecord {
  id: string;
  loaded: LoadedMesh;
  bodyHandle: number | null;
}

const BG_COLOR = 0x0a0a0c;
const FOG_NEAR = 14;
const FOG_FAR = 48;
const GROUND_HALF_SIZE = 30;

export class Viewer {
  readonly scene: THREE.Scene;
  readonly camera: THREE.PerspectiveCamera;
  readonly renderer: THREE.WebGLRenderer;
  readonly canvas: HTMLCanvasElement;
  readonly objects: Map<string, ObjectRecord> = new Map();
  readonly ground: THREE.Mesh;
  readonly gridHelper: THREE.GridHelper;

  private loadedScene: LoadedScene | null = null;
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

    const rim = new THREE.DirectionalLight(0xe46b45, 0.35);
    rim.position.set(-5, 3, -4);
    this.scene.add(rim);

    const groundGeo = new THREE.PlaneGeometry(GROUND_HALF_SIZE, GROUND_HALF_SIZE);
    const groundMat = new THREE.MeshStandardMaterial({
      color: 0x14141a,
      roughness: 0.95,
      metalness: 0.0,
    });
    this.ground = new THREE.Mesh(groundGeo, groundMat);
    this.ground.rotation.x = -Math.PI / 2;
    this.ground.receiveShadow = true;
    this.scene.add(this.ground);

    this.gridHelper = new THREE.GridHelper(20, 40, 0xe46b45, 0x1e1e24);
    const gridMat = this.gridHelper.material as THREE.Material;
    gridMat.transparent = true;
    gridMat.opacity = 0.25;
    this.gridHelper.position.y = 0.001;
    this.scene.add(this.gridHelper);

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

  /**
   * Attach a pre-resolved scene. The Object3D roots come in positioned in
   * world coords; we do NOT mutate their child tree (preserves baked glTF
   * textures).
   */
  loadScene(scene: LoadedScene): void {
    this.clear();
    this.loadedScene = scene;

    // Position the ground + grid at the scene's floor level.
    this.ground.position.y = scene.groundY;
    this.gridHelper.position.y = scene.groundY + 0.001;

    for (const m of scene.meshes) {
      tagTree(m.object3d, m.id);
      m.object3d.traverse((c) => {
        const mesh = c as THREE.Mesh;
        if (mesh.isMesh) {
          mesh.castShadow = true;
          mesh.receiveShadow = true;
        }
      });
      this.scene.add(m.object3d);
      this.objects.set(m.id, { id: m.id, loaded: m, bodyHandle: null });
    }

    if (scene.cameraHint) {
      const p = scene.cameraHint.position;
      const t = scene.cameraHint.target;
      this.camera.position.set(p[0], p[1], p[2]);
      this.camera.lookAt(t[0], t[1], t[2]);
    }
  }

  currentScene(): LoadedScene | null {
    return this.loadedScene;
  }

  clear(): void {
    for (const rec of this.objects.values()) {
      this.scene.remove(rec.loaded.object3d);
      disposeRecursive(rec.loaded.object3d);
    }
    this.objects.clear();
    this.clearHighlight();
  }

  setHighlight(id: string | null): void {
    this.clearHighlight();
    if (id === null) return;
    const rec = this.objects.get(id);
    if (!rec) return;
    this.highlightTarget = rec.loaded.object3d;
    rec.loaded.object3d.traverse((c) => {
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
    for (const rec of this.objects.values()) meshes.push(rec.loaded.object3d);
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

function tagTree(root: THREE.Object3D, id: string) {
  root.userData.objectId = id;
  root.traverse((c) => {
    c.userData.objectId = id;
  });
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
