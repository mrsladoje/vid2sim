# Stream 02 — Reconstruction (Person 2)

> Bounded context: everything between a `PerceptionFrame` bundle on disk and a set of `ReconstructedObject`s with watertight, scale-correct, world-posed meshes. Person 2 is on the **critical path** — if they slip, Person 3 runs on stub data longer.

See also: [`../PHASED_PLAN.md`](../PHASED_PLAN.md), [`../adr/ADR-002-hybrid-depth-fusion.md`](../adr/ADR-002-hybrid-depth-fusion.md), [`../adr/ADR-003-image-to-3d-diffusion.md`](../adr/ADR-003-image-to-3d-diffusion.md), [`../VID2SIM_PRD.md`](../VID2SIM_PRD.md) §7 Stage A (host side) + §7 Stage B.

---

## 1. Scope & bounded context

**Owns**
- DA3METRIC-LARGE monocular depth on M3 Max MPS.
- Stereo+DA3 per-frame RANSAC fusion (`stereo ≈ s · DA3 + t`).
- RTAB-Map visual-inertial odometry on host via the DepthAI v3 host-node integration (early-access preview — may require `depthai-core` develop branch).
- Per-object point cloud extraction (mask × fused depth → back-project in camera intrinsics, transform to world frame via VIO pose).
- Hunyuan3D 2.1 mesh completion (via `Brainkeys/Hunyuan3D-2.1-mac` fork, PyTorch 2.5.1, SDPA).
- TripoSG 1.5B (VAST-AI, Jan 2026, MIT) fallback path — rectified-flow, MPS-compatible, better than SF3D at similar throughput.
- Stable Fast 3D (SF3D) emergency-only fallback.
- ICP scale + pose alignment of generated unit-cube meshes to the observed point cloud (seed with 2D-bbox centroid + class prior; constrain azimuth-only search).
- Mesh decimation to ≤50k tris.

**Does not own**
- On-device perception — Person 1.
- `scene.json` assembly, physics, exporters — Person 3.
- CoACD 1.0.10 convex decomposition — Person 3 (may call it, but Person 3 owns the pipeline).
- Browser viewer — Person 4.

---

## 2. Ubiquitous language (Reconstruction)

| Term | Meaning |
|---|---|
| **Fused depth** | Per-pixel metric depth = RANSAC-aligned combination of LENS stereo and DA3 monocular. |
| **World frame** | A single coordinate frame, +Y up, origin at first-keyframe camera, metres. |
| **VIO pose** | 6-DoF camera pose per keyframe from RTAB-Map (host). |
| **Object point cloud** | Per-track-id set of world-frame 3D points produced by back-projecting the masked fused depth. |
| **Raw mesh** | Hunyuan3D / TripoSG / SF3D output: watertight mesh in [-0.5, 0.5]³ unit cube, UV-mapped, PBR. |
| **Aligned mesh** | Raw mesh after ICP `(s, R, t)` so it coincides with its object point cloud in world frame. |
| **ReconstructedObject** | A single object's final bundle: aligned glTF mesh, PBR textures, class label, track id, 2D RGB crop, provenance. |
| **Provenance** | `{depth_origin, pose_origin, mesh_origin, icp_residual, s_stereo_da3, t_stereo_da3}` for each object. |

---

## 3. External dependencies (consumed)

| From | What | Format |
|---|---|---|
| Person 1 | PerceptionFrame bundle | `data/captures/<session_id>/` per `spec/perception_frame.md` |
| Person 3 | `scene.json` schema fields we must populate | `spec/scene.schema.json` (to know mesh path convention, provenance field names) |
| — | DA3METRIC-LARGE weights | HuggingFace `depth-anything/DA3METRIC-LARGE` |
| — | Hunyuan3D 2.1 weights + TripoSG 1.5B weights + SF3D weights | HuggingFace |

Anti-corruption layer: nothing from DepthAI SDK types leaks into the `ReconstructedObject` contract. Point clouds are `numpy.ndarray` or `open3d.PointCloud` internally; the exported artifact is plain files.

---

## 4. External deliverables (produced)

The **ReconstructedObject set**, one per segmented track:

```
data/reconstructed/<session_id>/
  world_pose.json                         # world frame definition, keyframe poses
  fused_depth/00000.npy                   # fused depth per frame (optional, debug)
  objects/
    <track_id>_<class>/
      mesh.glb                            # aligned, decimated, UV-mapped, PBR
      mesh.ply                            # debug point cloud
      crop.jpg                            # best-view RGB crop (for Person 3's VLM)
      object_manifest.json                # see below
```

`object_manifest.json` schema:
```json
{
  "track_id": 17,
  "class": "chair",
  "best_crop_path": "crop.jpg",
  "mesh_path": "mesh.glb",
  "transform_world": {"translation": [x,y,z], "rotation_quat": [x,y,z,w], "scale": 1.0},
  "bbox_world": {"min": [x,y,z], "max": [x,y,z]},
  "provenance": {
    "depth_origin": "stereo+da3_ransac",
    "pose_origin": "rtabmap_vio|single_keyframe",
    "mesh_origin": "hunyuan3d_2.1|triposg_1.5b|sf3d",
    "icp_residual": 0.012,
    "s_stereo_da3": 1.04,
    "t_stereo_da3": 0.02
  }
}
```

Consumers: Person 3 reads the ReconstructedObject set exclusively. Person 4 reads nothing from here directly.

---

## 5. Phased tasks

| Phase | Window | Task | Subtask | Artifact |
|---|---|---|---|---|
| G0 | H0–H2 | Bootstrap | `src/reconstruction/` package, pytest skeleton, MPS smoke test | green CI |
| G0 | H0–H2 | DA3 bench on M3 Max | Run DA3METRIC-LARGE on one synthetic 1080p frame; record wall-clock | `docs/reconstruction/bench_da3.md` |
| G0 | H0–H2 | Hunyuan3D bench on M3 Max | Run `Brainkeys` fork on one RGB crop; record per-object wall time | `docs/reconstruction/bench_hunyuan.md` (**hard gate for budget**) |
| G0 | H0–H2 | Freeze ReconstructedObject contract with Person 3 | Draft `spec/reconstructed_object.md`; walk through with Person 3 | `spec/reconstructed_object.md` v1.0 |
| **G0 gate** | H2 | Benches logged, contract signed | — | — |
| G1 | H2–H6 | RANSAC depth fusion module | Classical `solve s, t via RANSAC over confident pixels` | `src/reconstruction/fusion.py` + unit tests with synthetic stereo/DA3 |
| G1 | H2–H6 | Back-projector | Intrinsics + depth → world-frame point cloud (identity pose for now) | `src/reconstruction/backproject.py` |
| G1 | H2–H6 | Stub `ReconstructedObject` emitter | Takes one mask + one frame, spits out a primitive-mesh fake (unit cube scaled to bbox) | `src/reconstruction/stub_emitter.py` — **unblocks Person 3** |
| G1 | H2–H6 | Hunyuan3D host harness | Lock MPS env, load model, one image → one mesh, cache weights | `src/reconstruction/hunyuan_runner.py` |
| **G1 gate** | H6 | Stub `ReconstructedObject` set exists; Person 3 can assemble a scene from it | — | — |
| G2 | H6–H12 | End-to-end on hero object | Read `hero_01` bundle → fused depth → point cloud → Hunyuan3D → ICP align → emit | `data/reconstructed/hero_01/objects/<id>_chair/` |
| G2 | H6–H12 | RTAB-Map VIO integration | Host node; if preview is unstable, fall back to single-keyframe pose | `src/reconstruction/vio.py` |
| G2 | H6–H12 | ICP scale+pose align | `open3d.registration_icp` with class-prior seed | `src/reconstruction/icp_align.py` |
| G2 | H6–H12 | TripoSG 1.5B fallback path | Same interface as Hunyuan runner; swappable via config | `src/reconstruction/triposg_runner.py` |
| G2 | H6–H12 | SF3D emergency fallback | Last-resort path; same interface | `src/reconstruction/sf3d_runner.py` |
| G2 | H6–H12 | Mesh decimation | `trimesh.simplify_quadric_decimation` to 50k tris | `src/reconstruction/decimate.py` |
| **G2 gate** | H12 | One real hero object has a correctly-scaled, world-posed mesh on disk; Person 3 loads it in their assembler | — | — |
| G3 | H12–H18 | Full demo scene (3–5 objects) | Batch run Hunyuan3D per object with cooldown gaps; TripoSG 1.5B fallback on any failure after one retry (SF3D emergency) | `data/reconstructed/demo_scene/` |
| G3 | H12–H18 | Thermal watchdog | Monitor MPS temps via `powermetrics`; pause between objects if >95°C | `src/reconstruction/thermal.py` |
| G3 | H12–H18 | Feature freeze | Stop adding new recovery paths after H18 | — |
| **G3 gate** | H18 | Full demo-scene ReconstructedObject set on disk, Person 3 confirms it assembles | — | — |
| G4 | H18–H22 | Tests to 80% on fusion + ICP | Synthetic fixtures, golden outputs | pytest coverage report |
| G4 | H18–H22 | Provenance audit | Every `object_manifest.json` has all provenance fields populated | `tests/reconstruction/test_provenance.py` |
| **G4 gate** | H22 | CI green; tests ≥80% on fusion + ICP (per PRD NFR) | — | — |
| G5 | H22–H24 | Demo standby | Pre-warm models, keep `data/reconstructed/demo_scene/` fresh | — |

---

## 6. Phase gates

| Gate | Automated check | Manual check | Artifact check | If red |
|---|---|---|---|---|
| G0 | DA3 bench completes; Hunyuan3D + TripoSG benches complete | Per-object wall time ≤60 s on one asset | `bench_hunyuan.md` filled | If Hunyuan3D >60 s/object: commit to TripoSG 1.5B as primary, cap hero objects at 2, notify Queen |
| G1 | `pytest src/reconstruction` green; fusion + backprojector unit tests pass on synthetic data | Stub mesh visible in Person 3's assembler | `spec/reconstructed_object.md` signed by Person 3; stub emitter works | Keep stub-only path alive until G2; Person 3 can start with fakes |
| G2 | ICP residual <3 cm on hero chair; mesh tris ≤50k; provenance populated | Open `mesh.glb` in Blender/VS Code preview, verify it looks like a chair | `data/reconstructed/hero_01/` exists | If ICP diverges: fall back to bbox-centred identity pose; flag in provenance; continue |
| G3 | Full-scene batch completes ≤ 90 s total wall-clock | Eyeball each mesh in preview | `data/reconstructed/demo_scene/` has 3–5 objects each with manifest | Drop to 3 objects; swap worst to TripoSG 1.5B (SF3D emergency); re-run |
| G4 | `pytest --cov=src/reconstruction` ≥80% on `fusion.py` + `icp_align.py`; mypy/ruff/black clean | — | All manifests validate | Drop non-critical tests; keep fusion+ICP as the hard 80% target |
| G5 | — | End-to-end dry-run from bundle to reconstructed set succeeds twice | — | Fall back to pre-rendered demo set |

---

## 7. Risk & fallback (stream-specific)

| Risk | Likelihood | Fallback |
|---|---|---|
| Hunyuan3D MPS runtime fails / >60 s per object | Medium | Switch to TripoSG 1.5B as primary (ADR-003), SF3D as emergency. Decision point **H10**. Accept slightly lower PBR quality; mesh is still watertight. |
| RTAB-Map VIO early-access host node won't converge | Medium | Fall back to single-keyframe pose: treat the first confident keyframe as world origin and only reconstruct objects visible in it. Pitch becomes "single-shot" not "multi-view." |
| ICP drifts on symmetric / untextured objects | Medium | Class-prior seed + azimuth-only search + iteration cap (100). If residual >5 cm, use bbox-centred identity pose and flag in provenance. |
| DA3 metric conversion gives wrong scale | Low | Unit tests against a known-distance target (ruler at 1 m) before G1. |
| M3 Max thermal throttle during batch | Medium | Serial Hunyuan3D runs with 10 s cooldowns. If `powermetrics` shows sustained throttle, switch remaining objects to TripoSG 1.5B (SF3D emergency). |
| Mesh exceeds 50k tris or WASM memory budget | Low | Decimation step is unconditional. If still too large, cap scene at 5 objects. |

---

## 8. Day-of-demo responsibilities

- Pre-run the full demo-scene reconstruction on the laptop an hour before pitch; cache everything.
- During pitch: if live reconstruction is part of the script, trigger it on cue; watch thermals silently.
- If live reconstruction fails: show the pre-rendered `data/reconstructed/demo_scene/` on disk; the pipeline is unchanged downstream.

---

## 9. Definition of done

- [ ] `spec/reconstructed_object.md` v1.0 frozen and signed.
- [ ] RANSAC fusion + ICP align each have ≥80% test coverage with synthetic fixtures.
- [ ] Hunyuan3D benchmark logged and per-object budget decision made by H10.
- [ ] Demo-scene ReconstructedObject set on disk with full provenance.
- [ ] Thermal watchdog active during batch runs.
- [ ] Stub emitter kept functional to H24 as a break-glass fallback for Person 3.
