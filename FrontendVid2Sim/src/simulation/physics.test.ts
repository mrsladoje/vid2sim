/** @vitest-environment happy-dom */
import { beforeAll, describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { Physics } from './physics';
import type { LoadedMesh, LoadedScene } from './types';
import type { ObjectRecord, Viewer } from './viewer';

describe('Physics drag controls', () => {
  beforeAll(async () => {
    const { default: RAPIER } = await import('@dimforge/rapier3d-compat');
    await RAPIER.init();
  });

  it('switches dragged bodies to kinematic motion and restores them on release', async () => {
    const mesh = makeLoadedMesh('crate_01', new THREE.Vector3(0, 0.6, 0));
    const viewer = makeViewer([mesh]);
    const physics = new Physics(viewer);
    await physics.init();
    physics.buildWorld(makeScene([mesh]));

    const startHeight = physics.startDrag('crate_01');
    expect(startHeight).toBeCloseTo(0.6, 5);

    const body = physics.getBodyFor('crate_01');
    expect(body?.isKinematic()).toBe(true);

    physics.moveDrag('crate_01', new THREE.Vector3(0.9, startHeight!, -0.4));
    physics.step(1 / 60);
    expect(body?.translation().x).toBeCloseTo(0.9, 2);
    expect(body?.translation().z).toBeCloseTo(-0.4, 2);

    physics.endDrag('crate_01');
    expect(body?.isDynamic()).toBe(true);
    expect(body?.linvel().x).toBeCloseTo(0, 5);
    expect(body?.linvel().y).toBeCloseTo(0, 5);
    expect(body?.linvel().z).toBeCloseTo(0, 5);
  });

  it('refuses to start drag on fixed bodies', async () => {
    const mesh = makeLoadedMesh('table_01', new THREE.Vector3(0, 0.4, 0), false);
    const viewer = makeViewer([mesh]);
    const physics = new Physics(viewer);
    await physics.init();
    physics.buildWorld(makeScene([mesh]));

    expect(physics.startDrag('table_01')).toBeNull();
    expect(physics.getBodyFor('table_01')?.isFixed()).toBe(true);
  });

  it('applies off-center impulses at the picked point', async () => {
    const mesh = makeLoadedMesh('crate_01', new THREE.Vector3(0, 0.6, 0));
    const viewer = makeViewer([mesh]);
    const physics = new Physics(viewer);
    await physics.init();
    physics.buildWorld(makeScene([mesh]));

    const body = physics.getBodyFor('crate_01')!;
    physics.applyImpulseAtPoint(
      'crate_01',
      new THREE.Vector3(0, 0, 3),
      new THREE.Vector3(0.15, 0.6, 0),
    );
    physics.step(1 / 60);

    expect(Math.abs(body.angvel().y)).toBeGreaterThan(0);
  });
});

function makeLoadedMesh(
  id: string,
  position: THREE.Vector3,
  isRigid = true,
): LoadedMesh {
  const object3d = new THREE.Mesh(
    new THREE.BoxGeometry(0.3, 0.3, 0.3),
    new THREE.MeshStandardMaterial(),
  );
  object3d.position.copy(position);
  object3d.updateMatrixWorld(true);
  return {
    id,
    object3d,
    label: id,
    classification: 'crate',
    bboxWorld: new THREE.Box3().setFromObject(object3d),
    meshOrigin: 'test',
    physics: {
      isRigid,
      massKg: 1.5,
      friction: 0.6,
      restitution: 0.1,
    },
  };
}

function makeScene(meshes: LoadedMesh[]): LoadedScene {
  return {
    displayName: 'test-scene',
    meshes,
    groundY: 0,
    gravityY: -9.81,
    groundMaterial: { friction: 0.8, restitution: 0.1 },
    isFallback: false,
  };
}

function makeViewer(meshes: LoadedMesh[]): Viewer {
  const scene = new THREE.Scene();
  const objects = new Map<string, ObjectRecord>();
  for (const mesh of meshes) {
    scene.add(mesh.object3d);
    objects.set(mesh.id, { id: mesh.id, loaded: mesh, bodyHandle: null });
  }
  return { scene, objects } as Viewer;
}
