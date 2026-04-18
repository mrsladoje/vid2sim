import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { SceneSpec, SceneObject } from "./types/scene";
import { buildPrimitiveMesh } from "./primitives";

export interface ObjectRecord {
  id: string;
  spec: SceneObject;
  mesh: THREE.Object3D;
  /** Rapier RigidBody handle — set by Physics after wiring. */
  bodyHandle: number | null;
}

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

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x1a1a22);
    this.scene.fog = new THREE.Fog(0x1a1a22, 15, 50);

    this.camera = new THREE.PerspectiveCamera(
      55,
      canvas.clientWidth / Math.max(canvas.clientHeight, 1),
      0.05,
      200,
    );
    this.camera.position.set(3.0, 2.2, 3.5);
    this.camera.lookAt(0, 0.4, 0);

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.0;

    const hemi = new THREE.HemisphereLight(0xbfd7ff, 0x404040, 0.55);
    this.scene.add(hemi);

    const sun = new THREE.DirectionalLight(0xffffff, 2.2);
    sun.position.set(4, 8, 4);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -6;
    sun.shadow.camera.right = 6;
    sun.shadow.camera.top = 6;
    sun.shadow.camera.bottom = -6;
    sun.shadow.camera.near = 0.5;
    sun.shadow.camera.far = 25;
    this.scene.add(sun);

    const groundGeo = new THREE.PlaneGeometry(30, 30);
    const groundMat = new THREE.MeshStandardMaterial({
      color: 0x404048,
      roughness: 0.95,
      metalness: 0.0,
    });
    this.ground = new THREE.Mesh(groundGeo, groundMat);
    this.ground.rotation.x = -Math.PI / 2;
    this.ground.receiveShadow = true;
    this.scene.add(this.ground);

    const gridHelper = new THREE.GridHelper(20, 40, 0x333333, 0x222222);
    (gridHelper.material as THREE.Material).transparent = true;
    (gridHelper.material as THREE.Material).opacity = 0.4;
    this.scene.add(gridHelper);

    this.selectionMaterial = new THREE.MeshStandardMaterial({
      color: 0xffcc33,
      emissive: 0x553300,
      roughness: 0.4,
      metalness: 0.1,
    });

    window.addEventListener("resize", () => this.resize());
  }

  resize(): void {
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    this.camera.aspect = w / Math.max(h, 1);
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
      const scale = obj.transform.scale;
      if (scale !== 1.0) mesh.scale.setScalar(scale);
      mesh.userData.objectId = obj.id;
      // Tag every descendant for raycast-based picking.
      mesh.traverse((c) => {
        c.userData.objectId = obj.id;
      });
      this.scene.add(mesh);
      this.objects.set(obj.id, {
        id: obj.id,
        spec: obj,
        mesh,
        bodyHandle: null,
      });
    }
  }

  private async buildMeshFor(obj: SceneObject, baseUrl: string): Promise<THREE.Object3D> {
    if (obj.mesh.startsWith("primitive:")) {
      return buildPrimitiveMesh(obj);
    }
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
      // Production expectation is a watertight .glb from Hunyuan3D/TripoSG.
      // If it fails mid-demo, fall back to a primitive so we never render nothing.
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

  /** Screen (pixel) coords → normalized device coords [-1, 1]. */
  ndcFromPixel(x: number, y: number, out: THREE.Vector2): THREE.Vector2 {
    const rect = this.canvas.getBoundingClientRect();
    out.x = ((x - rect.left) / rect.width) * 2 - 1;
    out.y = -((y - rect.top) / rect.height) * 2 + 1;
    return out;
  }

  /** Raycast from mouse, find the top-level object record hit (if any). */
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

  /** Project a screen point onto a world-space ground-parallel plane at the given height. */
  planeIntersect(clientX: number, clientY: number, height: number): THREE.Vector3 | null {
    const ndc = new THREE.Vector2();
    this.ndcFromPixel(clientX, clientY, ndc);
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(ndc, this.camera);
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -height);
    const hit = new THREE.Vector3();
    if (raycaster.ray.intersectPlane(plane, hit)) {
      return hit;
    }
    return null;
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
