# ReconstructedObject Contract v1.0

**Owner:** Person 2 (Stream 02 — Reconstruction).
**Consumer:** Person 3 (Stream 03 — Scene Assembly) via `src/scene/reconstructed.py`.
**Status:** Frozen at G0. Additive-only after G1.

This is the second cross-stream contract in VID2SIM (C2 in
`docs/PHASED_PLAN.md`). It is the anti-corruption boundary between the
reconstruction pipeline and scene assembly: no Python type from Stream 02
leaks across — the boundary is a directory of files on disk.

## 1. Directory layout

```
data/reconstructed/<session_id>/
  reconstructed.json                 # top-level index (schema §3)
  world_pose.json                    # world-frame definition + keyframe poses
  fused_depth/XXXXX.npy              # optional debug: per-frame fused depth (mm)
  objects/
    <track_id>_<class>/
      mesh.glb                       # aligned, decimated, UV+PBR watertight
      mesh.ply                       # optional debug: object point cloud
      crop.jpg                       # best-view RGB crop for Stream 03's VLM
      object_manifest.json           # rich provenance (schema §4)
```

Stream 03 only reads `reconstructed.json` and the `mesh.glb` / `crop.jpg`
paths it points at. The per-object `object_manifest.json` is internal to
Stream 02 provenance + debug.

## 2. `world_pose.json`

```json
{
  "up_axis": "y",
  "unit": "meters",
  "origin_keyframe": 0,
  "keyframes": [
    {"frame": 0, "translation": [0,0,0], "rotation_quat": [0,0,0,1]}
  ],
  "pose_origin": "rtabmap_vio"
}
```

`pose_origin` ∈ {`rtabmap_vio`, `single_keyframe`, `identity`}.

## 3. `reconstructed.json` (Stream 03 reads this)

```json
{
  "session_id": "hero_01",
  "objects": [
    {
      "id": "chair_17",
      "class": "chair",
      "mesh_path": "objects/17_chair/mesh.glb",
      "crop_image_path": "objects/17_chair/crop.jpg",
      "mesh_origin": "hunyuan3d_2.1",
      "center": [0.42, 0.0, 1.13],
      "rotation_quat": [0.0, 0.0, 0.0, 1.0],
      "bbox_min": [-0.25, 0.0, -0.25],
      "bbox_max": [0.25, 0.9, 0.25],
      "lowest_points": [[0.0, 0.0, 0.0]]
    }
  ]
}
```

Field contract (matches `src/scene/reconstructed.py:ReconstructedObject`):

| Field | Type | Notes |
|---|---|---|
| `id` | str | Unique within session. Convention: `<class>_<track_id>`. |
| `class` | str | From the `class_prompts` list in the PerceptionFrame manifest. |
| `mesh_path` | str | Relative to session dir. MUST exist. |
| `crop_image_path` | str | Relative to session dir. MUST exist. |
| `mesh_origin` | enum | One of `hunyuan3d_2.1`, `triposg_1.5b`, `sf3d`, `identity`. Matches `spec/scene.schema.json`. |
| `center` | [x,y,z] | World-frame centroid, metres. |
| `rotation_quat` | [x,y,z,w] | World-frame rotation. |
| `bbox_min`, `bbox_max` | [x,y,z] | AABB of the aligned mesh in world frame. |
| `lowest_points` | list of [x,y,z] | Optional ground-contact seeds for Stream 03 ground estimation. |

## 4. `object_manifest.json` (internal, per object)

```json
{
  "track_id": 17,
  "class": "chair",
  "id": "chair_17",
  "best_crop_path": "crop.jpg",
  "mesh_path": "mesh.glb",
  "transform_world": {"translation": [0.42,0,1.13], "rotation_quat": [0,0,0,1], "scale": 1.0},
  "bbox_world": {"min": [-0.25,0,-0.25], "max": [0.25,0.9,0.25]},
  "provenance": {
    "depth_origin": "stereo+da3_ransac",
    "pose_origin": "rtabmap_vio",
    "mesh_origin_detail": "runpod:hunyuan3d_2.1",
    "mesh_origin": "hunyuan3d_2.1",
    "icp_residual": 0.012,
    "s_stereo_da3": 1.04,
    "t_stereo_da3": 0.02,
    "ran_on": "runpod",
    "pod_id": "a100-eu-1",
    "generation_s": 7.8,
    "alignment_s": 0.41,
    "decimate_input_tris": 188432,
    "decimate_output_tris": 49710
  }
}
```

`provenance.mesh_origin_detail` ∈ {`runpod:hunyuan3d_2.1`, `runpod:triposg_1.5b`,
`local:sf3d`, `stub`, `identity`}.
`provenance.mesh_origin` MUST be the scene-schema-aligned enum form
(`hunyuan3d_2.1`, `triposg_1.5b`, `sf3d`, `identity`); the two agree 1-to-1
modulo prefix, except `stub` → `identity`.
`provenance.ran_on` ∈ {`runpod`, `local`, `stub`}.

## 5. Quality guarantees

- `mesh.glb` is watertight after Stage B + ICP alignment (Hunyuan3D/TripoSG
  always are by construction; SF3D fallback verified post-mesh).
- `mesh.glb` has ≤ 50 000 triangles after decimation.
- `bbox_world` is world-frame, matches the observed point cloud's AABB
  within the ICP residual.
- Every object written to disk MUST have every field above populated —
  no partial manifests. A missing field is a hard failure in Stream 03.

## 6. Change policy

- v1.0 frozen at G0 (2026-04-18).
- Additive-only after G1 (H6). Breaking changes after H6 require Queen
  signoff + notification to Stream 03 and Stream 04.
