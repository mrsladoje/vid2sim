import { describe, it, expect, vi } from 'vitest';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import {
  ReconstructedFetchError,
  ReconstructedJsonSource,
  computeGroundY,
  resolveBaseUrl,
  validateManifest,
  type ReconstructedManifest,
  type ReconstructedObjectEntry,
} from './reconstructedSource';

const FIXTURE: ReconstructedManifest = {
  session_id: 'rec_01_sf3d',
  objects: [
    {
      id: 'bottle_01',
      class: 'bottle',
      mesh_path: 'objects/1_bottle/mesh.glb',
      crop_image_path: 'objects/1_bottle/crop.jpg',
      mesh_origin: 'sf3d',
      center: [0.146, 0.095, 0.672],
      rotation_quat: [0.35, 0.29, 0.13, 0.88],
      bbox_min: [0.142, 0.088, 0.668],
      bbox_max: [0.15, 0.102, 0.676],
      lowest_points: [[0.146, 0.088, 0.672]],
    },
    {
      id: 'cup_02',
      class: 'cup',
      mesh_path: 'objects/2_cup/mesh.glb',
      crop_image_path: 'objects/2_cup/crop.jpg',
      mesh_origin: 'sf3d',
      center: [-0.019, 0.131, 0.666],
      rotation_quat: [0.33, 0.36, 0.11, 0.87],
      bbox_min: [-0.031, 0.116, 0.653],
      bbox_max: [-0.007, 0.145, 0.679],
      lowest_points: [[-0.019, 0.116, 0.666]],
    },
  ],
};

function makeJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makeFakeLoader(): GLTFLoader {
  const fake = {
    loadAsync: vi.fn(async () => {
      const scene = new THREE.Group();
      // One child mesh with a red material so we can assert it survives.
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(0.05, 0.1, 0.05),
        new THREE.MeshStandardMaterial({ color: 0xff0000 }),
      );
      scene.add(mesh);
      return { scene, scenes: [scene] } as unknown as { scene: THREE.Group };
    }),
  } as unknown as GLTFLoader;
  return fake;
}

describe('ReconstructedJsonSource', () => {
  it('loads manifest + meshes and applies center + rotation_quat to Object3D roots', async () => {
    const fetchImpl = vi.fn(async () => makeJsonResponse(FIXTURE));
    const loader = makeFakeLoader();
    const source = new ReconstructedJsonSource({
      manifestUrl: 'http://localhost/scenes/rec_01_sf3d/reconstructed.json',
      fetchImpl: fetchImpl as unknown as typeof fetch,
      gltfLoader: loader,
    });

    const scene = await source.load();

    expect(fetchImpl).toHaveBeenCalledWith(
      'http://localhost/scenes/rec_01_sf3d/reconstructed.json',
    );
    expect(scene.meshes).toHaveLength(2);
    expect(scene.isFallback).toBe(false);

    const bottle = scene.meshes[0];
    expect(bottle.id).toBe('bottle_01');
    expect(bottle.classification).toBe('bottle');
    expect(bottle.label).toBe('Bottle');
    expect(bottle.meshOrigin).toBe('sf3d');
    expect(bottle.object3d.position.x).toBeCloseTo(0.146, 3);
    expect(bottle.object3d.position.y).toBeCloseTo(0.095, 3);
    expect(bottle.object3d.position.z).toBeCloseTo(0.672, 3);
    expect(bottle.object3d.quaternion.x).toBeCloseTo(0.35, 2);
    expect(bottle.object3d.quaternion.w).toBeCloseTo(0.88, 2);

    expect(bottle.bboxWorld.min.y).toBeCloseTo(0.088, 3);
    expect(bottle.bboxWorld.max.y).toBeCloseTo(0.102, 3);

    // GLB child tree must remain intact (tests the "don't rebuild geometry" rule).
    const childMeshes: THREE.Mesh[] = [];
    bottle.object3d.traverse((c) => {
      if ((c as THREE.Mesh).isMesh) childMeshes.push(c as THREE.Mesh);
    });
    expect(childMeshes.length).toBe(1);
    expect((childMeshes[0].material as THREE.MeshStandardMaterial).color.getHex()).toBe(0xff0000);

    // Ground Y = min(lowest_points.y) across objects.
    expect(scene.groundY).toBeCloseTo(0.088, 3);

    // Each root Object3D is tagged so the viewer's raycaster can resolve it.
    expect(bottle.object3d.userData.objectId).toBe('bottle_01');
  });

  it('throws ReconstructedFetchError on 404', async () => {
    const fetchImpl = vi.fn(async () => new Response('not found', { status: 404 }));
    const source = new ReconstructedJsonSource({
      manifestUrl: 'http://localhost/missing.json',
      fetchImpl: fetchImpl as unknown as typeof fetch,
      gltfLoader: makeFakeLoader(),
    });

    await expect(source.load()).rejects.toBeInstanceOf(ReconstructedFetchError);
  });

  it('rejects malformed manifests', () => {
    expect(() => validateManifest({ objects: 'nope' }, 'test')).toThrow();
    expect(() => validateManifest(null, 'test')).toThrow();
    expect(() =>
      validateManifest(
        { objects: [{ id: 'x', mesh_path: 'm', center: [0, 0], rotation_quat: [0, 0, 0, 1], bbox_min: [0, 0, 0], bbox_max: [1, 1, 1] }] },
        'test',
      ),
    ).toThrow(/invalid center/);
  });

  it('computeGroundY falls back to bbox_min.y when lowest_points is missing', () => {
    const objs: ReconstructedObjectEntry[] = [
      {
        id: 'a', class: 'cup', mesh_path: '', mesh_origin: 'sf3d',
        center: [0, 0, 0], rotation_quat: [0, 0, 0, 1],
        bbox_min: [0, 0.5, 0], bbox_max: [1, 1, 1],
      },
      {
        id: 'b', class: 'cup', mesh_path: '', mesh_origin: 'sf3d',
        center: [0, 0, 0], rotation_quat: [0, 0, 0, 1],
        bbox_min: [0, -0.1, 0], bbox_max: [1, 1, 1],
        lowest_points: [[0, 0.02, 0], [0, -0.05, 0]],
      },
    ];
    expect(computeGroundY(objs)).toBeCloseTo(-0.05, 3);
  });

  it('resolveBaseUrl yields the manifest folder', () => {
    const base = resolveBaseUrl('http://x/scenes/rec_01_sf3d/reconstructed.json');
    expect(base).toBe('http://x/scenes/rec_01_sf3d/');
  });
});
