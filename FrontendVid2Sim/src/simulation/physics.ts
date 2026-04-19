import * as THREE from "three";
import RAPIER from "@dimforge/rapier3d-compat";
import type { SceneSpec, SceneObject } from "./types";
import type { Viewer, ObjectRecord } from "./viewer";

export interface ExtraBody {
  body: RAPIER.RigidBody;
  mesh: THREE.Mesh;
  ttl?: number;
}

export class Physics {
  private rapier: typeof RAPIER | null = null;
  world: RAPIER.World | null = null;
  private initialSpec: SceneSpec | null = null;
  private objectBodies: Map<string, RAPIER.RigidBody> = new Map();
  private readonly extras: ExtraBody[] = [];
  private readonly ballMat: THREE.MeshStandardMaterial;
  private bodyIdToObjectId: Map<number, string> = new Map();
  private gravityOverride: number | null = null;
  private frictionScale = 1;
  private readonly viewer: Viewer;

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

  buildWorld(spec: SceneSpec): void {
    if (!this.rapier) throw new Error("Physics.init() not called");
    this.teardown();
    this.initialSpec = spec;

    const g = spec.world.gravity;
    const gy = this.gravityOverride ?? g[1];
    this.world = new this.rapier.World({ x: g[0], y: gy, z: g[2] });

    const groundBody = this.world.createRigidBody(this.rapier.RigidBodyDesc.fixed());
    const groundCol = this.rapier.ColliderDesc.cuboid(50, 0.05, 50)
      .setTranslation(0, -0.05, 0)
      .setFriction(spec.ground.material.friction * this.frictionScale)
      .setRestitution(spec.ground.material.restitution);
    this.world.createCollider(groundCol, groundBody);

    for (const obj of spec.objects) {
      const rec = this.viewer.objects.get(obj.id);
      if (!rec) continue;
      const body = this.createBodyForObject(obj);
      rec.bodyHandle = body.handle;
      this.objectBodies.set(obj.id, body);
      this.bodyIdToObjectId.set(body.handle, obj.id);
    }
  }

  private createBodyForObject(obj: SceneObject): RAPIER.RigidBody {
    if (!this.world || !this.rapier) throw new Error("world not initialized");
    const t = obj.transform.translation;
    const q = obj.transform.rotation_quat;

    const bodyDesc = obj.physics.is_rigid
      ? this.rapier.RigidBodyDesc.dynamic()
          .setTranslation(t[0], t[1], t[2])
          .setRotation({ x: q[0], y: q[1], z: q[2], w: q[3] })
          .setAdditionalMass(0)
          .setLinearDamping(0.05)
          .setAngularDamping(0.1)
      : this.rapier.RigidBodyDesc.fixed()
          .setTranslation(t[0], t[1], t[2])
          .setRotation({ x: q[0], y: q[1], z: q[2], w: q[3] });

    const body = this.world.createRigidBody(bodyDesc);

    const colDesc = this.colliderDescFor(obj);
    colDesc
      .setFriction(obj.physics.friction * this.frictionScale)
      .setRestitution(obj.physics.restitution)
      .setDensity(this.estimateDensity(obj));
    this.world.createCollider(colDesc, body);
    return body;
  }

  private colliderDescFor(obj: SceneObject): RAPIER.ColliderDesc {
    if (!this.rapier) throw new Error("rapier not ready");
    const c = obj.collider;
    switch (c.shape) {
      case "sphere":
        return this.rapier.ColliderDesc.ball(c.radius ?? 0.1);
      case "cylinder":
        return this.rapier.ColliderDesc.cylinder((c.height ?? 0.2) / 2, c.radius ?? 0.1);
      case "capsule":
        return this.rapier.ColliderDesc.capsule((c.height ?? 0.2) / 2, c.radius ?? 0.1);
      case "box":
      case "mesh":
      default: {
        const he = c.half_extents ?? [0.25, 0.25, 0.25];
        return this.rapier.ColliderDesc.cuboid(he[0], he[1], he[2]);
      }
    }
  }

  private estimateDensity(obj: SceneObject): number {
    const c = obj.collider;
    let volume: number;
    if (c.shape === "sphere") {
      const r = c.radius ?? 0.1;
      volume = (4 / 3) * Math.PI * r * r * r;
    } else if (c.shape === "cylinder" || c.shape === "capsule") {
      const r = c.radius ?? 0.1;
      const h = c.height ?? 0.2;
      volume = Math.PI * r * r * h;
    } else {
      const he = c.half_extents ?? [0.25, 0.25, 0.25];
      volume = he[0] * 2 * he[1] * 2 * he[2] * 2;
    }
    return volume > 0 ? Math.max(obj.physics.mass_kg / volume, 1) : 1000;
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
      rec.mesh.position.set(p.x, p.y, p.z);
      rec.mesh.quaternion.set(r.x, r.y, r.z, r.w);
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
      .setLinvel(0, -0.5, 0);
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

  reset(): void {
    if (this.initialSpec) this.buildWorld(this.initialSpec);
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
    if (this.initialSpec) this.buildWorld(this.initialSpec);
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
