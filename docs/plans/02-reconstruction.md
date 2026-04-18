# Stream 02 — Reconstruction (Person 2)

> Bounded context: everything between a `PerceptionFrame` bundle on disk and a set of `ReconstructedObject`s with watertight, scale-correct, world-posed meshes. Person 2 is on the **critical path** — if they slip, Person 3 runs on stub data longer.

See also: [`../PHASED_PLAN.md`](../PHASED_PLAN.md), [`../adr/ADR-002-hybrid-depth-fusion.md`](../adr/ADR-002-hybrid-depth-fusion.md), [`../adr/ADR-003-image-to-3d-diffusion.md`](../adr/ADR-003-image-to-3d-diffusion.md), [`../adr/ADR-009-runpod-remote-diffusion.md`](../adr/ADR-009-runpod-remote-diffusion.md), [`../VID2SIM_PRD.md`](../VID2SIM_PRD.md) §7 Stage A (host side) + §7 Stage B.

---

## 1. Scope & bounded context

**Owns**
- DA3METRIC-LARGE monocular depth on M3 Max MPS (local).
- Stereo+DA3 per-frame RANSAC fusion (`stereo ≈ s · DA3 + t`).
- RTAB-Map visual-inertial odometry on host via the DepthAI v3 host-node integration (early-access preview — may require `depthai-core` develop branch).
- Per-object point cloud extraction (mask × fused depth → back-project in camera intrinsics, transform to world frame via VIO pose).
- **RunPod pod client + FastAPI mesh-generation server image (ADR-009).** Pod hosts Hunyuan3D 2.1 (primary) and TripoSG 1.5B (in-pod fallback). Local thin client posts `{rgb_crop, mask, model}` → receives `.glb`. Pod pre-warm script + health-check ritual are Stream-02 responsibilities.
- Stable Fast 3D (SF3D) **local last-resort fallback** on M3 Max MPS — fires only if the pod is unreachable.
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
| **Raw mesh** | Hunyuan3D / TripoSG / SF3D output: watertight mesh in [-0.5, 0.5]³ unit cube, UV-mapped, PBR. Hunyuan3D and TripoSG run on RunPod (ADR-009); SF3D runs locally on MPS only as last-resort fallback. |
| **Pod** | The RunPod persistent GPU instance (A100 40GB baseline, H100 if available) running the mesh-generation FastAPI server. Pre-warmed T-60 min before demo. |
| **Aligned mesh** | Raw mesh after ICP `(s, R, t)` so it coincides with its object point cloud in world frame. |
| **ReconstructedObject** | A single object's final bundle: aligned glTF mesh, PBR textures, class label, track id, 2D RGB crop, provenance. |
| **Provenance** | `{depth_origin, pose_origin, mesh_origin, icp_residual, s_stereo_da3, t_stereo_da3}` for each object. |

---

## 3. External dependencies (consumed)

| From | What | Format |
|---|---|---|
| Person 1 | PerceptionFrame bundle | `data/captures/<session_id>/` per `spec/perception_frame.md` |
| Person 3 | `scene.json` schema fields we must populate | `spec/scene.schema.json` (to know mesh path convention, provenance field names) |
| — | DA3METRIC-LARGE weights | HuggingFace `depth-anything/DA3METRIC-LARGE` (loaded on M3 Max) |
| — | Hunyuan3D 2.1 + TripoSG 1.5B weights | HuggingFace — baked into the RunPod pod image on a persistent volume |
| — | SF3D weights | HuggingFace — cached locally on M3 Max for last-resort fallback only |
| — | RunPod account + API key + persistent pod | `RUNPOD_API_KEY` env var; pod endpoint URL persisted in `config/runpod.yaml` |

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
    "mesh_origin": "runpod:hunyuan3d_2.1|runpod:triposg_1.5b|local:sf3d|stub",
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
| G0 | H0–H2 | **RunPod pod image + bring-up (ADR-009)** | Dockerfile with Hunyuan3D 2.1 + TripoSG 1.5B + FastAPI server; push to RunPod; spin up A100 pod with persistent volume for weights | `infra/runpod/Dockerfile`, `infra/runpod/server.py`, `config/runpod.yaml` |
| G0 | H0–H2 | **RunPod latency + wall-time bench** | One crop → pod → glb, measured end-to-end including network on venue-proxy wifi; both Hunyuan3D and TripoSG | `docs/reconstruction/bench_runpod.md` (**hard gate for budget**) |
| G0 | H0–H2 | Local SF3D smoke test | Confirm SF3D weights load + one mesh generates on M3 Max MPS for last-resort fallback | `docs/reconstruction/bench_sf3d_local.md` |
| G0 | H0–H2 | Freeze ReconstructedObject contract with Person 3 | Draft `spec/reconstructed_object.md`; walk through with Person 3 | `spec/reconstructed_object.md` v1.0 |
| **G0 gate** | H2 | Pod live; round-trip <20 s/object end-to-end; SF3D local fallback boots; contract signed | — | — |
| G1 | H2–H6 | RANSAC depth fusion module | Classical `solve s, t via RANSAC over confident pixels` | `src/reconstruction/fusion.py` + unit tests with synthetic stereo/DA3 |
| G1 | H2–H6 | Back-projector | Intrinsics + depth → world-frame point cloud (identity pose for now) | `src/reconstruction/backproject.py` |
| G1 | H2–H6 | Stub `ReconstructedObject` emitter | Takes one mask + one frame, spits out a primitive-mesh fake (unit cube scaled to bbox) | `src/reconstruction/stub_emitter.py` — **unblocks Person 3** |
| G1 | H2–H6 | **RunPod client** | Thin HTTP client: `generate_mesh(rgb_crop, mask, model) → glb_bytes`; retry + timeout + circuit-breaker to SF3D fallback; provenance tag per call | `src/reconstruction/runpod_client.py` |
| G1 | H2–H6 | Local SF3D fallback runner | Wrap SF3D on MPS behind the same interface as the RunPod client | `src/reconstruction/sf3d_runner.py` |
| **G1 gate** | H6 | Stub `ReconstructedObject` set exists; Person 3 can assemble a scene from it; RunPod client round-trips one real crop | — | — |
| G2 | H6–H12 | End-to-end on hero object | Read `hero_01` bundle → fused depth → point cloud → RunPod Hunyuan3D → ICP align → emit | `data/reconstructed/hero_01/objects/<id>_chair/` |
| G2 | H6–H12 | RTAB-Map VIO integration | Host node; if preview is unstable, fall back to single-keyframe pose | `src/reconstruction/vio.py` |
| G2 | H6–H12 | ICP scale+pose align | `open3d.registration_icp` with class-prior seed | `src/reconstruction/icp_align.py` |
| G2 | H6–H12 | TripoSG 1.5B fallback path | Already in-pod; just switch the `model` arg in the client | `src/reconstruction/runpod_client.py` (config flag) |
| G2 | H6–H12 | Mesh decimation | `trimesh.simplify_quadric_decimation` to 50k tris (runs locally on returned glb) | `src/reconstruction/decimate.py` |
| **G2 gate** | H12 | One real hero object has a correctly-scaled, world-posed mesh on disk; Person 3 loads it in their assembler | — | — |
| G3 | H12–H18 | Full demo scene (3–5 objects) | Batch run via RunPod client in parallel (pod handles serialisation); TripoSG in-pod fallback on retry; local SF3D emergency if pod unreachable | `data/reconstructed/demo_scene/` |
| G3 | H12–H18 | **Pod health watchdog** | Periodic `GET /healthz`; if 2 consecutive failures, trip circuit-breaker to local SF3D; record in provenance | `src/reconstruction/pod_watchdog.py` |
| G3 | H12–H18 | Feature freeze | Stop adding new recovery paths after H18 | — |
| **G3 gate** | H18 | Full demo-scene ReconstructedObject set on disk, Person 3 confirms it assembles | — | — |
| G4 | H18–H22 | Tests to 80% on fusion + ICP | Synthetic fixtures, golden outputs; RunPod client tested against a recorded mock server | pytest coverage report |
| G4 | H18–H22 | Provenance audit | Every `object_manifest.json` has all provenance fields populated incl. `mesh_origin` with correct `runpod:*`/`local:*`/`stub` tag | `tests/reconstruction/test_provenance.py` |
| **G4 gate** | H22 | CI green; tests ≥80% on fusion + ICP (per PRD NFR) | — | — |
| G5 | H22–H24 | **Pod pre-warm (T-60 min)** | Start pod; `GET /healthz`; run one warm-up inference; confirm round-trip <300 ms; keep `data/reconstructed/demo_scene/` fresh | — |

---

## 6. Phase gates

| Gate | Automated check | Manual check | Artifact check | If red |
|---|---|---|---|---|
| G0 | DA3 local bench + RunPod bench both complete; pod `GET /healthz` returns 200; one end-to-end crop→glb round trip on tether | End-to-end per-object wall time (incl. network) ≤20 s on Hunyuan3D, ≤15 s on TripoSG; SF3D one-shot on MPS completes | `bench_runpod.md`, `bench_sf3d_local.md`, `config/runpod.yaml` filled | If RunPod round-trip >30 s: escalate to H100 pod region; if pod cannot be booked, fall back to local SF3D as primary and cap hero objects at 2, notify Queen |
| G1 | `pytest src/reconstruction` green; fusion + backprojector unit tests pass on synthetic data; RunPod client returns a real glb on one hero crop | Stub mesh visible in Person 3's assembler | `spec/reconstructed_object.md` signed by Person 3; stub emitter works; RunPod client retry + SF3D circuit-breaker exercised in test | Keep stub-only path alive until G2; Person 3 can start with fakes |
| G2 | ICP residual <3 cm on hero chair; mesh tris ≤50k; provenance populated with correct `runpod:hunyuan3d_2.1` tag | Open `mesh.glb` in Blender/VS Code preview, verify it looks like a chair | `data/reconstructed/hero_01/` exists | If ICP diverges: fall back to bbox-centred identity pose; flag in provenance; continue. If RunPod down: exercise SF3D fallback once on hero to confirm the path still produces a valid object. |
| G3 | Full-scene batch completes ≤ 90 s total wall-clock (incl. all RunPod round-trips); pod_watchdog green throughout | Eyeball each mesh in preview | `data/reconstructed/demo_scene/` has 3–5 objects each with manifest | Drop to 3 objects; swap any failing object to TripoSG in-pod; if pod itself fails, route remaining to local SF3D |
| G4 | `pytest --cov=src/reconstruction` ≥80% on `fusion.py` + `icp_align.py`; mypy/ruff/black clean | — | All manifests validate; every `mesh_origin` tag is one of the legal enum values | Drop non-critical tests; keep fusion+ICP as the hard 80% target |
| G5 | Pod pre-warmed T-60 min, health-check green at T-10 min, round-trip <300 ms | End-to-end dry-run from bundle to reconstructed set succeeds twice over the venue network | — | Fall back to pre-rendered demo set |

---

## 7. Risk & fallback (stream-specific)

| Risk | Likelihood | Fallback |
|---|---|---|
| **RunPod pod unreachable at demo time (venue wifi blocks it, region outage, auth expired)** | Medium | Pod pre-warmed T-60 min with health-check; tether via phone as first backup link; local SF3D on M3 Max MPS as last-resort mesh generator; stub emitter as break-glass. Decision ritual: if pod_watchdog trips during live pitch, client auto-routes to SF3D — no manual intervention. |
| RunPod pod round-trip >20 s/object even after warmup | Low | Try H100 pod in a closer region; reduce crop resolution (384→256 px); drop to TripoSG in-pod (faster than Hunyuan3D); cap hero objects at 3. Decision point **H10**. |
| Hunyuan3D / TripoSG produce bad mesh on a specific crop | Medium | Retry once, then swap to the other in-pod model via `model` arg; if both fail, emit stub primitive and flag in provenance. |
| RTAB-Map VIO early-access host node won't converge | Medium | Fall back to single-keyframe pose: treat the first confident keyframe as world origin and only reconstruct objects visible in it. Pitch becomes "single-shot" not "multi-view." |
| ICP drifts on symmetric / untextured objects | Medium | Class-prior seed + azimuth-only search + iteration cap (100). If residual >5 cm, use bbox-centred identity pose and flag in provenance. |
| DA3 metric conversion gives wrong scale | Low | Unit tests against a known-distance target (ruler at 1 m) before G1. |
| Mesh exceeds 50k tris or WASM memory budget | Low | Decimation step is unconditional. If still too large, cap scene at 5 objects. |
| RunPod cost overrun | Low | Pod is ~$2–4/hr; spin down immediately post-demo. Cap single-session runtime at 6 hours. |

---

## 8. Day-of-demo responsibilities

- **T-60 min:** start RunPod pod; confirm weights mounted from persistent volume; run one warm-up inference on a cached crop; log wall time + network round-trip.
- **T-30 min:** pre-run the full demo-scene reconstruction end-to-end (RunPod path); cache `data/reconstructed/demo_scene/`; verify each `mesh_origin` is `runpod:hunyuan3d_2.1`.
- **T-10 min:** `GET /healthz` green; round-trip <300 ms; tether hotspot primed as secondary link.
- **During pitch:** if live reconstruction is part of the script, trigger it on cue; watch `pod_watchdog` output silently.
- **If RunPod fails mid-pitch:** client auto-routes to local SF3D (expect ~30 s/object — plan the script so this degradation is survivable for 3 objects).
- **If everything fails:** show the pre-rendered `data/reconstructed/demo_scene/` cached at T-30; the downstream pipeline is unchanged.
- **Post-demo:** stop the pod to end billing.

---

## 9. Definition of done

- [ ] `spec/reconstructed_object.md` v1.0 frozen and signed.
- [ ] RANSAC fusion + ICP align each have ≥80% test coverage with synthetic fixtures.
- [ ] RunPod pod image built, weights staged on persistent volume, FastAPI endpoint spec'd, round-trip bench logged (ADR-009).
- [ ] Per-object budget decision locked by H10 (Hunyuan3D vs TripoSG in-pod).
- [ ] Local SF3D last-resort fallback verified; circuit-breaker from RunPod client exercised.
- [ ] Demo-scene ReconstructedObject set on disk with full provenance, all `mesh_origin` tags correct.
- [ ] `pod_watchdog` active during batch runs.
- [ ] Stub emitter kept functional to H24 as a break-glass fallback for Person 3.
