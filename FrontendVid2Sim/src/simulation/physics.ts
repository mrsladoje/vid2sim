import * as THREE from "three";
import RAPIER from "@dimforge/rapier3d-compat";
import type { LoadedMesh, LoadedScene } from "./types";
import type { Viewer, ObjectRecord } from "./viewer";

export interface ExtraBody {
  body: RAPIER.RigidBody;
  mesh: THREE.Mesh;
  ttl?: number;
}

export class Physics {
  private rapier: typeof RAPIER | null = null;
  world: RAPIER.World | null = null;
  private currentScene: LoadedScene | null = null;
  private initialPoses: Map<string, { pos: THREE.Vector3; quat: THREE.Quaternion }> =
    new Map();
  private objectBodies: Map<string, RAPIER.RigidBody> = new Map();
  private readonly extras: ExtraBody[] = [];
  private readonly ballMat: THREE.MeshStandardMaterial;
  private bodyIdToObjectId: Map<number, string> = new Map();
  private gravityOverride: number | null = null;
  private frictionScale = 1;
  private readonly viewer: Viewer;
  private dragBodyId: string | null = null;

  constructor(viewer: Viewer) {
    this.viewer = viewer;
    this.ballMat = new THREE.MeshStandardMaterial({
      color: 0xe46b45,
      emissive: 0x2a0f05,
      roughness: 0.35,
      metalness: 0.1,
    });
  }

  async init(): Promise<void> {
    if (this.rapier) return;
    await RAPIER.init();
    this.rapier = RAPIER;
  }

  buildWorld(scene: LoadedScene): void {
    if (!this.rapier) throw new Error("Physics.init() not called");
    const isFirstBuild = this.currentScene !== scene;
    this.teardown();
    this.currentScene = scene;

    if (isFirstBuild) {
      this.initialPoses.clear();
      for (const mesh of scene.meshes) {
        this.initialPoses.set(mesh.id, {
          pos: mesh.object3d.position.clone(),
          quat: mesh.object3d.quaternion.clone(),
        });
      }
    } else {
      // Restore object3d transforms to their snapshotted initial pose.
      for (const mesh of scene.meshes) {
        const initial = this.initialPoses.get(mesh.id);
        if (!initial) continue;
        mesh.object3d.position.copy(initial.pos);
        mesh.object3d.quaternion.copy(initial.quat);
      }
    }

    const gy = this.gravityOverride ?? scene.gravityY;
    this.world = new this.rapier.World({ x: 0, y: gy, z: 0 });

    const groundBody = this.world.createRigidBody(this.rapier.RigidBodyDesc.fixed());
    const groundCol = this.rapier.ColliderDesc.cuboid(50, 0.05, 50)
      .setTranslation(0, scene.groundY - 0.05, 0)
      .setFriction(scene.groundMaterial.friction * this.frictionScale)
      .setRestitution(scene.groundMaterial.restitution);
    this.world.createCollider(groundCol, groundBody);

    for (const mesh of scene.meshes) {
      const rec = this.viewer.objects.get(mesh.id);
      if (!rec) continue;
      const body = this.createBodyForMesh(mesh);
      rec.bodyHandle = body.handle;
      this.objectBodies.set(mesh.id, body);
      this.bodyIdToObjectId.set(body.handle, mesh.id);
    }
  }

  private createBodyForMesh(mesh: LoadedMesh): RAPIER.RigidBody {
    if (!this.world || !this.rapier) throw new Error("world not initialized");

    const pos = mesh.object3d.position;
    const q = mesh.object3d.quaternion;
    const physics = mesh.physics ?? defaultPhysics();

    const bodyDesc = physics.isRigid
      ? this.rapier.RigidBodyDesc.dynamic()
          .setTranslation(pos.x, pos.y, pos.z)
          .setRotation({ x: q.x, y: q.y, z: q.z, w: q.w })
          .setAdditionalMass(0)
          .setLinearDamping(0.05)
          .setAngularDamping(0.1)
      : this.rapier.RigidBodyDesc.fixed()
          .setTranslation(pos.x, pos.y, pos.z)
          .setRotation({ x: q.x, y: q.y, z: q.z, w: q.w });

    const body = this.world.createRigidBody(bodyDesc);

    // Collider is a convex hull of the AABB, in the body's local frame. We
    // can't use the world-space bboxWorld directly because the body already
    // carries the world translation + rotation.
    const colDesc = this.colliderDescFor(mesh);
    if (colDesc) {
      colDesc
        .setFriction(physics.friction * this.frictionScale)
        .setRestitution(physics.restitution)
        .setDensity(this.estimateDensity(mesh));
      this.world.createCollider(colDesc, body);
    }
    return body;
  }

  /**
   * Build a collider shape in LOCAL space (relative to the body). We derive
   * the half-extents from the body-local AABB of the Object3D — this is
   * simple, robust, and matches "convex-hull of the glTF" closely enough for
   * tabletop-scale demos.
   */
  private colliderDescFor(mesh: LoadedMesh): RAPIER.ColliderDesc | null {
    if (!this.rapier) return null;
    const local = computeLocalBox(mesh.object3d);
    if (!local) return null;
    const size = local.max.clone().sub(local.min);
    const halfExtents = new THREE.Vector3(
      Math.max(size.x * 0.5, 0.01),
      Math.max(size.y * 0.5, 0.01),
      Math.max(size.z * 0.5, 0.01),
    );
    const center = local.min.clone().add(local.max).multiplyScalar(0.5);
    const desc = this.rapier.ColliderDesc.cuboid(
      halfExtents.x,
      halfExtents.y,
      halfExtents.z,
    );
    if (center.lengthSq() > 1e-8) {
      desc.setTranslation(center.x, center.y, center.z);
    }
    return desc;
  }

  private estimateDensity(mesh: LoadedMesh): number {
    const physics = mesh.physics ?? defaultPhysics();
    const size = mesh.bboxWorld.getSize(new THREE.Vector3());
    const volume = Math.max(size.x, 0.02) * Math.max(size.y, 0.02) * Math.max(size.z, 0.02);
    return volume > 0 ? Math.max(physics.massKg / volume, 1) : 1000;
  }

  step(dt: number): void {
    if (!this.world) return;
    this.world.timestep = Math.min(dt, 1 / 30);
    this.world.step();
    this.syncMeshesFromBodies();
    this.tickExtras(dt);
  }

  private syncMeshesFromBodies(): void {
    for (const [id, body] of this.objectBodies) {
      const rec = this.viewer.objects.get(id);
      if (!rec) continue;
      const p = body.translation();
      const r = body.rotation();
      rec.loaded.object3d.position.set(p.x, p.y, p.z);
      rec.loaded.object3d.quaternion.set(r.x, r.y, r.z, r.w);
    }
    for (const extra of this.extras) {
      const p = extra.body.translation();
      const r = extra.body.rotation();
      extra.mesh.position.set(p.x, p.y, p.z);
      extra.mesh.quaternion.set(r.x, r.y, r.z, r.w);
    }
  }

  private tickExtras(dt: number): void {
    for (let i = this.extras.length - 1; i >= 0; i--) {
      const e = this.extras[i];
      if (e.ttl !== undefined) {
        e.ttl -= dt;
        if (e.ttl <= 0) this.removeExtraAt(i);
      }
    }
  }

  private removeExtraAt(i: number): void {
    if (!this.world) return;
    const e = this.extras[i];
    this.world.removeRigidBody(e.body);
    this.viewer.scene.remove(e.mesh);
    e.mesh.geometry.dispose();
    this.extras.splice(i, 1);
  }

  dropBall(worldPos: THREE.Vector3, radius = 0.08, mass = 0.3): void {
    if (!this.world || !this.rapier) return;
    const desc = this.rapier.RigidBodyDesc.dynamic()
      .setTranslation(worldPos.x, worldPos.y, worldPos.z)
      .setLinvel(0, -0.5, 0)
      .setCcdEnabled(true);
    const body = this.world.createRigidBody(desc);
    const col = this.rapier.ColliderDesc.ball(radius)
      .setFriction(0.5)
      .setRestitution(0.7)
      .setDensity(mass / ((4 / 3) * Math.PI * radius * radius * radius));
    this.world.createCollider(col, body);

    const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 24, 18), this.ballMat);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    this.viewer.scene.add(mesh);

    this.extras.push({ body, mesh, ttl: 12 });
  }

  applyImpulse(id: string, impulse: THREE.Vector3): void {
    const body = this.objectBodies.get(id);
    if (!body) return;
    body.applyImpulse({ x: impulse.x, y: impulse.y, z: impulse.z }, true);
  }

  applyImpulseAtPoint(id: string, impulse: THREE.Vector3, point: THREE.Vector3): void {
    const body = this.objectBodies.get(id);
    if (!body) return;
    body.applyImpulseAtPoint(
      { x: impulse.x, y: impulse.y, z: impulse.z },
      { x: point.x, y: point.y, z: point.z },
      true,
    );
  }

  startDrag(id: string): number | null {
    if (!this.rapier) return null;
    const body = this.objectBodies.get(id);
    if (!body || !body.isDynamic()) return null;
    body.setLinvel({ x: 0, y: 0, z: 0 }, true);
    body.setAngvel({ x: 0, y: 0, z: 0 }, true);
    body.setBodyType(this.rapier.RigidBodyType.KinematicPositionBased, true);
    this.dragBodyId = id;
    return body.translation().y;
  }

  moveDrag(id: string, target: THREE.Vector3): void {
    const body = this.objectBodies.get(id);
    if (!body || this.dragBodyId !== id || !body.isKinematic()) return;
    body.setNextKinematicTranslation({ x: target.x, y: target.y, z: target.z });
    body.setAngvel({ x: 0, y: 0, z: 0 }, true);
  }

  endDrag(id: string): void {
    if (!this.rapier) return;
    const body = this.objectBodies.get(id);
    if (!body) return;
    if (body.isKinematic()) {
      body.setBodyType(this.rapier.RigidBodyType.Dynamic, true);
    }
    body.setLinvel({ x: 0, y: 0, z: 0 }, true);
    body.setAngvel({ x: 0, y: 0, z: 0 }, true);
    if (this.dragBodyId === id) this.dragBodyId = null;
  }

  reset(): void {
    if (!this.currentScene) return;
    this.buildWorld(this.currentScene);
  }

  setGravity(y: number): void {
    this.gravityOverride = y;
    if (this.world) {
      const g = this.world.gravity;
      this.world.gravity = { x: g.x, y, z: g.z };
    }
  }

  setFrictionScale(scale: number): void {
    this.frictionScale = Math.max(scale, 0);
    if (this.currentScene) this.buildWorld(this.currentScene);
  }

  teardown(): void {
    if (this.world) {
      for (const extra of this.extras.splice(0)) {
        this.viewer.scene.remove(extra.mesh);
        extra.mesh.geometry.dispose();
      }
      this.world.free();
      this.world = null;
    }
    this.objectBodies.clear();
    this.bodyIdToObjectId.clear();
    this.dragBodyId = null;
    for (const rec of this.viewer.objects.values()) {
      rec.bodyHandle = null;
    }
  }

  bodyCount(): number {
    if (!this.world) return 0;
    return this.objectBodies.size + this.extras.length;
  }

  getBodyFor(id: string): RAPIER.RigidBody | undefined {
    return this.objectBodies.get(id);
  }

  recordsById(): Map<string, ObjectRecord> {
    return this.viewer.objects;
  }
}

function defaultPhysics() {
  return { isRigid: true, massKg: 0.5, friction: 0.5, restitution: 0.15 };
}

/**
 * Body-local AABB of an Object3D. We compute the world-space AABB and then
 * project it into the root's local frame using the inverse of its world
 * matrix. Not perfectly tight under rotation, but good enough for a cuboid
 * physics proxy — and avoids walking the geometry buffers.
 */
function computeLocalBox(root: THREE.Object3D): THREE.Box3 | null {
  const worldBox = new THREE.Box3().setFromObject(root);
  if (worldBox.isEmpty()) return null;

  root.updateMatrixWorld(true);
  const inv = new THREE.Matrix4().copy(root.matrixWorld).invert();
  const local = new THREE.Box3();
  const corners: THREE.Vector3[] = [
    new THREE.Vector3(worldBox.min.x, worldBox.min.y, worldBox.min.z),
    new THREE.Vector3(worldBox.min.x, worldBox.min.y, worldBox.max.z),
    new THREE.Vector3(worldBox.min.x, worldBox.max.y, worldBox.min.z),
    new THREE.Vector3(worldBox.min.x, worldBox.max.y, worldBox.max.z),
    new THREE.Vector3(worldBox.max.x, worldBox.min.y, worldBox.min.z),
    new THREE.Vector3(worldBox.max.x, worldBox.min.y, worldBox.max.z),
    new THREE.Vector3(worldBox.max.x, worldBox.max.y, worldBox.min.z),
    new THREE.Vector3(worldBox.max.x, worldBox.max.y, worldBox.max.z),
  ];
  for (const c of corners) {
    c.applyMatrix4(inv);
    local.expandByPoint(c);
  }
  return local;
}
