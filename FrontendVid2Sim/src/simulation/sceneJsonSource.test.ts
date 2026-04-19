import { describe, it, expect, vi } from 'vitest';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import {
  SceneJsonFetchError,
  SceneJsonSource,
  resolveBaseUrl,
  validateSceneSpec,
} from './sceneJsonSource';
import type { SceneSpec } from './types';

const ASSEMBLED_FIXTURE: SceneSpec = {
  version: '1.0',
  world: { gravity: [0, -9.81, 0], up_axis: 'y', unit: 'meters' },
  ground: { type: 'plane', normal: [0, 1, 0], material: { friction: 0.8, restitution: 0.1 } },
  camera_pose: { translation: [0, 1.2, 0], rotation_quat: [0, 0, 0, 1] },
  objects: [
    {
      id: 'bottle_01',
      class: 'bottle',
      mesh: 'meshes/bottle_01.glb',
      material_class: 'plastic',
      transform: {
        translation: [0.146, 0.138, 0.672],
        rotation_quat: [0, 0, 0, 1], // identity — Bug 5 fix applied upstream
        scale: 1.0,
      },
      collider: {
        shape: 'mesh',
        convex_decomposition: true,
      },
      physics: { mass_kg: 0.5, friction: 0.3, restitution: 0.3, is_rigid: true },
      source: { mesh_origin: 'sf3d', physics_origin: 'lookup', vlm_reasoning: '' },
    },
    {
      id: 'cup_02',
      class: 'cup',
      mesh: 'meshes/cup_02.glb',
      material_class: 'ceramic',
      transform: {
        translation: [-0.019, 0.113, 0.666],
        rotation_quat: [0, 0, 0, 1],
        scale: 1.0,
      },
      collider: { shape: 'mesh', convex_decomposition: true },
      physics: { mass_kg: 0.25, friction: 0.5, restitution: 0.2, is_rigid: true },
      source: { mesh_origin: 'sf3d', physics_origin: 'lookup', vlm_reasoning: '' },
    },
  ],
};

function makeJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/**
 * Fake loader that returns a Group containing a child mesh with a realistic
 * "baked" node transform (simulating what the per-object staged GLB carries).
 * Lets us assert that we don't mutate the child tree.
 */
function makeFakeLoader(): GLTFLoader {
  return {
    loadAsync: vi.fn(async () => {
      const scene = new THREE.Group();
      // Intermediate node carrying the staged transform (Stream 03 Bug 6 territory).
      const stagedNode = new THREE.Object3D();
      stagedNode.position.set(0.01, 0.02, 0.03);
      stagedNode.scale.setScalar(0.5);
      stagedNode.userData.staged = true;

      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(0.1, 0.1, 0.1),
        new THREE.MeshStandardMaterial({
          color: 0x00ff00,
          map: new THREE.DataTexture(new Uint8Array([255, 0, 0, 255]), 1, 1),
        }),
      );
      stagedNode.add(mesh);
      scene.add(stagedNode);
      return { scene, scenes: [scene] } as unknown as { scene: THREE.Group };
    }),
  } as unknown as GLTFLoader;
}

describe('SceneJsonSource', () => {
  it('loads per-object GLBs and applies translation + identity rotation (Bug 5 safe)', async () => {
    const fetchImpl = vi.fn(async () => makeJsonResponse(ASSEMBLED_FIXTURE));
    const loader = makeFakeLoader();
    const source = new SceneJsonSource({
      manifestUrl: 'http://localhost/scenes/rec_01_sf3d_assembled/scene.json',
      fetchImpl: fetchImpl as unknown as typeof fetch,
      gltfLoader: loader,
    });

    const scene = await source.load();

    expect(scene.meshes).toHaveLength(2);
    expect(scene.isFallback).toBe(false);
    expect(scene.groundY).toBe(0); // assembler already snap-to-ground'd (Bug 4 safe)
    expect(scene.gravityY).toBeCloseTo(-9.81, 2);

    const bottle = scene.meshes[0];
    expect(bottle.id).toBe('bottle_01');
    expect(bottle.classification).toBe('bottle');
    expect(bottle.label).toBe('Bottle');
    expect(bottle.meshOrigin).toBe('sf3d');
    expect(bottle.physics?.massKg).toBe(0.5);
    expect(bottle.physics?.friction).toBe(0.3);
    expect(bottle.physics?.isRigid).toBe(true);

    // Per-object GLB loaded, not the composed scene.glb (Bug 6 avoidance).
    expect((loader.loadAsync as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      'http://localhost/scenes/rec_01_sf3d_assembled/meshes/bottle_01.glb',
    );

    // Translation applied to the root.
    expect(bottle.object3d.position.x).toBeCloseTo(0.146, 3);
    expect(bottle.object3d.position.y).toBeCloseTo(0.138, 3);
    expect(bottle.object3d.position.z).toBeCloseTo(0.672, 3);
    // Identity quat applied (no-op, but proves we respect the scene.json contract).
    expect(bottle.object3d.quaternion.x).toBe(0);
    expect(bottle.object3d.quaternion.y).toBe(0);
    expect(bottle.object3d.quaternion.z).toBe(0);
    expect(bottle.object3d.quaternion.w).toBe(1);
  });

  it('preserves the staged node tree (textures + baked transforms — Bug 2 + Bug 6 safe)', async () => {
    const fetchImpl = vi.fn(async () => makeJsonResponse(ASSEMBLED_FIXTURE));
    const loader = makeFakeLoader();
    const source = new SceneJsonSource({
      manifestUrl: 'http://localhost/a/scene.json',
      fetchImpl: fetchImpl as unknown as typeof fetch,
      gltfLoader: loader,
    });

    const scene = await source.load();
    const bottle = scene.meshes[0];

    // The staged intermediate node must survive untouched — this is what was
    // being DROPPED by Stream 03's buggy composed-gltf path. On our side we
    // load per-object, so it should always be intact.
    let stagedFound = false;
    let meshFound = 0;
    let textureFound = 0;
    bottle.object3d.traverse((c) => {
      if (c.userData.staged) {
        stagedFound = true;
        expect(c.position.x).toBeCloseTo(0.01, 4);
        expect(c.scale.x).toBeCloseTo(0.5, 4);
      }
      const m = c as THREE.Mesh;
      if (m.isMesh) {
        meshFound += 1;
        const mat = m.material as THREE.MeshStandardMaterial;
        if (mat.map) textureFound += 1;
      }
    });
    expect(stagedFound).toBe(true);
    expect(meshFound).toBe(1);
    expect(textureFound).toBe(1);
  });

  it('produces ONE Object3D per scene object (no monolithic scene.glb)', async () => {
    const fetchImpl = vi.fn(async () => makeJsonResponse(ASSEMBLED_FIXTURE));
    const loader = makeFakeLoader();
    const source = new SceneJsonSource({
      manifestUrl: 'http://localhost/a/scene.json',
      fetchImpl: fetchImpl as unknown as typeof fetch,
      gltfLoader: loader,
    });

    const scene = await source.load();

    // Distinct roots → physics.ts will create one Rapier body per mesh.
    // This is the concrete "no full-scene-as-brick" guarantee.
    expect(scene.meshes[0].object3d).not.toBe(scene.meshes[1].object3d);
    expect(scene.meshes[0].id).not.toBe(scene.meshes[1].id);

    // Each root is tagged so raycaster picking resolves to one object.
    expect(scene.meshes[0].object3d.userData.objectId).toBe('bottle_01');
    expect(scene.meshes[1].object3d.userData.objectId).toBe('cup_02');
  });

  it('rejects non-JSON responses (Vite SPA fallback detection)', async () => {
    const fetchImpl = vi.fn(
      async () =>
        new Response('<!DOCTYPE html><html></html>', {
          status: 200,
          headers: { 'Content-Type': 'text/html' },
        }),
    );
    const source = new SceneJsonSource({
      manifestUrl: 'http://localhost/missing/scene.json',
      fetchImpl: fetchImpl as unknown as typeof fetch,
      gltfLoader: makeFakeLoader(),
    });

    await expect(source.load()).rejects.toBeInstanceOf(SceneJsonFetchError);
  });

  it('rejects malformed scene specs', () => {
    expect(() => validateSceneSpec({ version: '0.5', objects: [] }, 't')).toThrow(/version/);
    expect(() => validateSceneSpec({ version: '1.0' }, 't')).toThrow(/objects/);
    expect(() =>
      validateSceneSpec(
        { version: '1.0', objects: [{ id: 'a', mesh: 'a.glb' }] },
        't',
      ),
    ).toThrow(/translation/);
  });

  it('resolveBaseUrl trims filename', () => {
    const base = resolveBaseUrl('http://x/scenes/rec_01_sf3d_assembled/scene.json');
    expect(base).toBe('http://x/scenes/rec_01_sf3d_assembled/');
  });
});
