# VID2SIM — Product Requirements Document

**Project codename:** VID2SIM
**Event:** DragonHack 2026, Ljubljana
**Team deliverable window:** ~24 hours
**Platform:** Luxonis OAK-4 D / D Pro (edge capture) + macOS Apple Silicon M3 Max (offline compute) + Web browser (demo)
**Status:** Draft v1 · 2026-04-18

---

## 1. Executive summary

VID2SIM turns a short RGB-D capture of a real-world scene into a portable, interactive physics simulation viewable in a browser. The pipeline fuses on-device stereo depth and monocular depth foundation models for robust metric geometry, uses image-to-3D diffusion to complete occluded geometry, and uses a vision-language model to infer per-object physics properties. The output is a simulator-agnostic scene specification (`scene.json`) with exporters to glTF, MJCF, USD, and MuJoCo.

**One-line pitch:** Polycam-for-physics — point a camera at a room, get an interactive simulation in under a minute.

---

## 2. Problem and motivation

Creating simulatable digital twins of real environments is (a) expensive (NVIDIA Omniverse + enterprise RTX), (b) manual (Blender + hand-authored URDFs), or (c) incomplete (Gaussian-splat research pipelines do not produce watertight meshes for conventional physics engines).

No shipped product exists that:
- Runs on an affordable edge camera
- Produces mesh-based, simulator-portable output
- Delivers an interactive result in a browser without backend compute

This gap is the project's reason for existing.

---

## 3. Goals and non-goals

### 3.1 Goals

1. Capture a static indoor scene with the OAK camera in ≤ 15 s.
2. Produce a watertight, physics-ready 3D scene in ≤ 90 s on M3 Max.
3. Let a judge interact with the scene in a browser at 60 FPS (drop ball, apply force, knock over).
4. Export the same scene to ≥ 2 professional simulator formats (glTF + MJCF at minimum; USD as stretch).
5. Ship a clean, tested, documented repository (Epilog target).

### 3.2 Non-goals

- Real-time end-to-end pipeline (processing is offline by design).
- Deformable / soft-body / fluid physics in v1.
- Dynamic scene capture (moving objects during capture).
- Outdoor / large-scale reconstruction.
- Commercial licensing or user accounts.

---

## 4. Users and use cases

| Persona | Scenario | Value |
|---|---|---|
| Training simulator vendor (Guardiaris) | Scan a room, train personnel on it | Cheap scenario authoring |
| Robotics researcher | Real-to-sim for policy pre-training | Avoid manual URDF work |
| Insurance / forensic investigator | Reconstruct an accident site | Geometry-anchored physics replay |
| Small-business safety | Shelf-tip / object-fall risk assessment | No CAD, no consultant |

Primary demo user: hackathon judges clicking inside a browser.

---

## 5. Hardware constraints (CRITICAL)

- The pipeline is designed against the **OAK-4 D** or **OAK-4 D Pro**. D Pro is preferred for its IR dot projector (resolves low-texture surfaces). Per Luxonis, OAK-4 D Pro NFOV depth error is <1.5% below 4 m, <3% at 4–8 m; ideal range 0.7–12 m; baseline 7.5 cm.
- The **OAK-4 S** ships with a stereo pair as well (per Luxonis shop page), but its IR projector and baseline are optimised for a different form factor; the pipeline was specced against the D Pro and has not been re-benchmarked on the S. Treat S as "probably works, unverified" and keep D Pro as the target.
- Local compute assumed: MacBook Pro M3 Max, 40-core GPU, 128 GB unified memory. No CUDA. No Isaac Sim.

---

## 6. System architecture

```
   ┌──────── OAK-4 D Pro (edge) ────────┐
   │ RGB + LENS stereo depth + IMU       │
   │ YOLOE-26 (on-NPU)                   │
   │ ObjectTracker 3D                    │
   │ SpatialLocationCalculator           │
   └──────────────────┬──────────────────┘
                      │ USB-C / PoE
                      ▼
   ┌──────── M3 Max (offline) ──────────┐
   │ A. Geometry recovery               │
   │ B. Geometry completion (diffusion) │
   │ C. Physics inference (VLM)         │
   │ D. Scene assembly + exporters       │
   │ E. Optional pretty-pass video diff │
   └──────────────────┬──────────────────┘
                      ▼
   ┌──────── Browser (Three.js) ────────┐
   │ Rapier WASM physics · 60 FPS       │
   └─────────────────────────────────────┘
```

The only contract between stages is the **`scene.json` spec** (see §9). All stages are independently testable.

---

## 7. Pipeline stages

### Stage A — Geometry recovery

| Concern | Decision |
|---|---|
| On-device depth | Luxonis LENS neural stereo on OAK-4 D Pro (NFOV: <1.5% error below 4 m; <3% at 4–8 m per Luxonis spec) |
| Monocular depth | Depth Anything 3 `DA3METRIC-LARGE` (`depth-anything/DA3METRIC-LARGE` on HF) on M3 Max via MPS; metric-native — convert with `depth_m = focal_px · net_out / 300` |
| Fusion method | Per-frame RANSAC least-squares `stereo ≈ s · DA3 + t`; DA3 fills stereo holes |
| Multi-frame consistency | RTAB-Map VIO via the DepthAI v3 VSLAM host-node example (marked "early-access preview"; may require `depthai-core` develop branch) consuming RGB+D+IMU |
| On-device segmentation | YOLOE-26 (+10 AP LVIS vs YOLO-World, 1.4× faster, Luxonis-supported on OAK-4 RVC4), prompt-driven open-vocabulary; optional edge SAM via EfficientSAM3 (RepViT/TinyViT backbones, MobileCLIP text encoder, ONNX+CoreML) — weights rolling out Q1 2026, bench at H0–H2 |
| Per-object point clouds | Mask × fused depth → back-project in camera intrinsics |

**Output**: a globally-consistent, metric-scale RGB-D + per-object point cloud set in a single world frame.

### Stage B — Geometry completion (image-to-3D diffusion)

| Concern | Decision |
|---|---|
| Primary model | Hunyuan3D 2.1 (Tencent) — DiT shape + Paint 2.1 PBR textures |
| Fallback model | TripoSG 1.5B (VAST-AI, Jan 2026, MIT) — rectified-flow, MPS-compatible, better quality than SF3D at similar throughput; Stable Fast 3D kept as emergency-only fallback if TripoSG fails on MPS |
| Execution | Local on M3 Max via MPS using the `Brainkeys/Hunyuan3D-2.1-mac` community fork (flash-attn → SDPA, removes CUDA deps, PyTorch 2.5.1) |
| Input | RGB crop + mask of each segmented object |
| Output | Watertight mesh in unit cube, UV-mapped, PBR maps |
| Scale recovery | ICP-style alignment of generated mesh to observed point cloud (s, R, t) |

**Rationale**: the camera sees only the front of each object; a physics engine needs a closed mesh. Diffusion hallucinates the back; the depth camera anchors scale and pose. Neither alone suffices — their composition is the engineering contribution.

### Stage C — Physics property inference

| Concern | Decision |
|---|---|
| Primary inference | VLM call (Claude Opus 4.7 primary, Gemini 3.1 Pro backup — Feb 2026, Video-MME 78.2%) with RGB crop + class + room context, wrapped with PhysQuantAgent-style visual prompting (visual markers overlaid on the crop — 2026 SOTA for physical-property estimation, arXiv 2603.16958; independent of the chosen VLM) |
| Cheap-path fallback | Qwen3-VL-30B-A3B-Instruct — open-weights, ~45× cheaper than Opus 4.7, 252 t/s, native JSON mode. Bench on 50-object set at H0–H2 before committing to Opus as primary. |
| Output schema | `{mass_kg, friction_coeff, restitution, material_class, is_rigid, reasoning}` |
| Fallback | Class-label lookup table (`chair → 5 kg, μ=0.5, wood, rigid`) |
| Confidence merge | Use VLM if confidence ≥ threshold; else fallback |

### Stage D — Scene assembly and exporters

Source of truth: **`scene.json`** (see §9). Generated artifacts:

| Target | Exporter | Consumer |
|---|---|---|
| `scene.glb` (+ sidecar physics JSON; `KHR_physics_rigid_bodies` is still a draft extension, not ratified) | Custom | Three.js + Rapier viewer |
| `scene.xml` | Custom MJCF emitter | MuJoCo / MJX |
| `scene.usd` (UsdPhysics schema) | `usd-core` | Isaac Sim, Omniverse, Unreal, Blender |
| `scene.py` | Template-driven | MuJoCo headless (`pip install mujoco` v3.3.2+, Apple-Silicon-native; MJX-on-Metal still experimental — stay on CPU MuJoCo) |

### Stage E — Pretty mode (optional, pre-recorded)

Render the MuJoCo / Rapier sim with depth + segmentation + normals buffers. Pass the depth sequence into **LTX-2-19B + IC-LoRA-Depth-Control** (primary, Lightricks, HF `Lightricks/LTX-2-19b-IC-LoRA-Depth-Control`, Mar 2026; fallback `Lightricks/LTX-Video-ICLoRA-depth-13b-0.9.7`) for motion-preserving prettification. CogVideoX-Fun-V1.5-Control retained only as a known-to-boot safety net if LTX-2 fails on MPS. Stretch: Wan 2.2 Fun Control (GGUF) — current MPS support is flaky. Budget 30–90 s of wall time per 1 s of output video. Overnight render only; not on the critical path.

---

## 8. Functional requirements

**FR-1 Capture.** The system shall acquire synchronized RGB, depth, and IMU frames from an OAK-4 D / D Pro at ≥ 15 FPS for 5–15 s.

**FR-2 Metric geometry.** The system shall produce per-object point clouds in a single metric world frame with error ≤ 3 cm at 2 m.

**FR-3 Object segmentation.** The system shall run open-vocabulary segmentation on-device for a user-provided class list.

**FR-4 Mesh completion.** For each segmented object, the system shall generate a watertight, UV-mapped mesh aligned to the observed point cloud.

**FR-5 Physics properties.** The system shall attach `{mass, friction, restitution, material}` to each object via VLM inference with fallback lookup.

**FR-6 Scene spec.** The system shall serialize all of the above into a typed `scene.json` conforming to the project schema.

**FR-7 Exporters.** The system shall export `scene.json` to glTF and MJCF. USD export is a stretch goal.

**FR-8 Browser viewer.** The system shall render `scene.glb` in a Three.js + Rapier viewer with interactive object manipulation at ≥ 60 FPS.

**FR-9 Demo script.** One recorded capture must be reproducibly converted to a working browser sim end-to-end.

## 8.1 Non-functional requirements

| NFR | Target |
|---|---|
| Total offline processing time | ≤ 90 s for a scene with ≤ 8 objects |
| Browser demo FPS | ≥ 60 |
| Repo test coverage (exporters + fusion math) | ≥ 80% |
| No CUDA, no Linux, no paid APIs beyond VLM inference | Enforced |
| Code style / CI | ruff/black + mypy + pytest + GitHub Actions |

---

## 9. Scene specification (`scene.json`)

This schema is the contract between stages. It must be frozen within the first two hours of the hackathon.

```json
{
  "version": "1.0",
  "world": {
    "gravity": [0, -9.81, 0],
    "up_axis": "y",
    "unit": "meters"
  },
  "ground": {
    "type": "plane",
    "normal": [0, 1, 0],
    "material": {"friction": 0.8, "restitution": 0.1}
  },
  "objects": [
    {
      "id": "chair_01",
      "class": "chair",
      "mesh": "meshes/chair_01.glb",
      "transform": {
        "translation": [0.42, 0.0, 1.13],
        "rotation_quat": [0, 0, 0, 1],
        "scale": 1.0
      },
      "collider": {
        "shape": "mesh",
        "convex_decomposition": true
      },
      "physics": {
        "mass_kg": 5.2,
        "friction": 0.45,
        "restitution": 0.2,
        "is_rigid": true
      },
      "material_class": "wood",
      "source": {
        "mesh_origin": "hunyuan3d_2.1",
        "physics_origin": "vlm",
        "vlm_reasoning": "visible grain on armrest..."
      }
    }
  ],
  "camera_pose": {
    "translation": [0, 1.2, 0],
    "rotation_quat": [0, 0, 0, 1]
  }
}
```

Schema file ships as `spec/scene.schema.json` (JSON Schema draft 2020-12). Every exporter has unit tests over canonical fixtures.

---

## 10. Technology stack

| Layer | Pick | Justification |
|---|---|---|
| Camera | OAK-4 D Pro | Stereo + IR projector + IMU + 52 TOPS NPU |
| On-device models | LENS, YOLOE-26, ObjectTracker, SpatialLocationCalc | First-class on Luxonis RVC4 |
| Host SLAM | RTAB-Map (via DepthAI v3 nodes) | Bundled integration |
| Monocular depth | Depth Anything 3 `DA3METRIC-LARGE` | Metric-native; fuses with stereo |
| Image→3D | Hunyuan3D 2.1 via `Brainkeys/Hunyuan3D-2.1-mac` fork (hero) + TripoSG 1.5B (fallback) + SF3D (emergency) | Watertight PBR; MPS-compatible |
| Physics LLM | Claude Opus 4.7 (primary), Gemini 3.1 Pro (backup), Qwen3-VL-30B-A3B-Instruct (cheap-path) — all wrapped with PhysQuantAgent-style visual prompting | Structured JSON output |
| Physics engine | Rapier (browser) + MuJoCo (export, v3.3.2+) | No-backend demo + headless option |
| Viewer | Three.js + Rapier WASM | 60 FPS, zero backend |
| Scene spec | Custom typed JSON + exporters | Beats fighting USD's Python API in 24 h |
| Pretty-pass (opt.) | LTX-2-19B + IC-LoRA-Depth-Control (CogVideoX-Fun-V1.5-Control safety net) | Motion-preserving prettification |

**Explicitly out of scope**: Isaac Sim (no Apple Silicon), Genesis (install friction), Gaussian-splatting pipelines (poor browser/physics story), video diffusion on the critical path.

---

## 11. Sponsor alignment

| Sponsor | Angle | Evidence in deliverable |
|---|---|---|
| **Luxonis** (Best Vision Hack) | On-device perception is essential, not decorative | LENS + YOLOE-26 + tracker all running on NPU |
| **Guardiaris** (Most Innovative) | Capture-to-trainer for military / safety sims | USD exporter + demo narrative |
| **Preskok** (B2B) | Plug-and-play edge product, no CAD | Scene spec + browser viewer |
| **Zero Days** (Fun & scalable) | Click in browser, watch physics | The demo itself |
| **Epilog** (Code quality) | Typed schema, exporter tests, CI, conventional commits | Repo structure |
| **Celtra** (API usage) | VLM + depth foundation model + geometry API | Visible in pipeline |
| **HYCU** (Safer world) | Training / forensic use-case framing | Pitch narrative |

---

## 12. Milestones (24 h)

| Window | Goal | Gate |
|---|---|---|
| H0–H2 | Repo setup, CI green, `scene.json` schema frozen, Three.js viewer loads a hand-written example | Viewer renders a chair + ball + ground |
| H2–H6 | Stage A MVP: capture script, stereo+DA3 fusion, per-object point clouds | PLY dump of one scan |
| H6–H12 | Stage B MVP: Hunyuan3D integration, scale alignment, mesh export | GLB of one object, correct size |
| H12–H16 | Stage C MVP: VLM physics props, fallback table | `scene.json` emitted end-to-end |
| H16–H20 | Integration + exporters + browser demo polish | Live demo runs |
| H20–H22 | Epilog polish: tests, docs, README, conventional commit history | CI all green |
| H22–H24 | Pitch deck, pretty-mode render, dry-run demo | Ready to present |

Hard rule: **no new features after H18**. Integration-only from then on.

---

## 13. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| OAK-4 S is the only camera available and its stereo pipeline behaves differently from D Pro | Medium | Re-benchmark at H0; if degraded, fall back to DA3-monocular only; pitch weakens but demo still works |
| Hunyuan3D 2.1 won't run cleanly on MPS in time | Medium | Swap in TripoSG 1.5B (rectified-flow, MPS-compatible, better than SF3D at similar throughput); SF3D is emergency-only if TripoSG also fails |
| LENS stereo noisy on thin objects | Low | DA3 takes over per-object where mask is thin |
| RTAB-Map VIO (early-access host node) fails to converge on short captures | Medium | Fall back to single-keyframe mode; on-device ObjectTracker gives coarse pose |
| ICP mesh alignment drifts on symmetric or untextured objects | Medium | Seed with 2D BBox centroid + YOLO class prior; limit search to azimuth; cap iterations |
| M3 Max thermal throttling during back-to-back Hunyuan3D runs | Medium | Run Stage B serially with cooldown gaps; monitor `powermetrics`; fall back to TripoSG 1.5B (SF3D emergency) if sustained throttle |
| Browser WASM memory ceiling on scenes with many large meshes | Low | Cap at 8 objects per scene (matches NFR); decimate Hunyuan3D output if >50k tris/object |
| Pretty-mode video diffusion takes too long | High | Pre-render the one demo clip overnight; keep off critical path |
| Demo laptop crashes mid-pitch | Low | Record a 30 s demo video as backup; play if needed |
| Captive venue network blocks VLM API | Medium | Tether via phone; fall back to class-label lookup table (ADR-005) |

---

## 14. Success metrics

**Must-have (demo day):**
- End-to-end pipeline runs on one scene, produces a working browser sim.
- Scene exports cleanly to at least glTF + MJCF.
- Repo passes CI with tests.

**Nice-to-have:**
- USD export viewable in Blender / Isaac Sim screenshot.
- Pretty-mode 15-s video rendered for pitch deck.
- Two independent scenes demo'd live.

**Win indicators:**
- Luxonis prize (Best Vision Hack).
- Category wins in Guardiaris, Preskok, and/or Epilog.
- Top-3 overall.

---

## 15. Open questions

1. **Which camera is actually in hand — S, D, or D Pro?** Blocking decision. Confirm before H0. OAK-4 S *does* have a stereo pair per the Luxonis shop page, but we have not benchmarked LENS on it; the pipeline was specced against D Pro.
2. **VLM call latency** — acceptable inside the 90 s budget? Needs a quick bench (batched single call vs. per-object).
3. **Mesh convex decomposition** — CoACD 1.0.10 (`pip install coacd`, CPU-only, collision-aware, fewer+tighter hulls than V-HACD) in Python during assembly, or in-browser before Rapier init? Pick at H10.
4. **Demo scene selection** — pick one reproducible room ahead of time (the venue table?) and rehearse the capture.
5. **Pretty-mode depth source** — use Rapier's depth buffer or re-render via MuJoCo? Decide at H16.
6. **Dynamic triangle-mesh colliders in Rapier** — Rapier supports trimesh colliders but they are primarily intended as *static* colliders; for dynamic rigid bodies we need convex decomposition. Confirm CoACD 1.0.10 tolerance per object class at H10.
7. **Hunyuan3D per-object wall time on MPS** — fork README claims feasibility but no hard number published; bench one asset at H0–H2 and set a per-object budget before committing to the 90 s scene target.
8. **KHR_physics_rigid_bodies** is still a draft glTF extension. We ship a sidecar physics JSON alongside the `.glb` to avoid depending on a non-ratified extension; revisit if the spec lands mid-hackathon.
9. **LTX-2-19B + IC-LoRA-Depth-Control per-frame latency on M3 Max MPS** — no public number; bench at H0–H2. Blocking for Stage E budget.
10. **Qwen3-VL-30B-A3B JSON-mode accuracy vs Claude Opus 4.7** — run 50-object physics-property test set at H0–H2 before committing to Opus as primary. Blocking.
11. **EfficientSAM3 Q1 2026 weights availability and accuracy on our target class list** — confirm release + bench at H0–H2. Blocking for edge-SAM path.
12. **TripoSG 1.5B per-asset wall time and mesh watertightness on M3 Max** — bench at H0–H2. Blocking for fallback commitment.
13. **DA3 RVC4 port status** — still no public `.dlc` as of April 2026; run off-device on M3 Max. Revisit if Luxonis ships a port.

---

## 16. References

- Depth Anything 3 — arXiv 2511.10647, github.com/ByteDance-Seed/Depth-Anything-3
- Hunyuan3D 2.1 — github.com/Tencent-Hunyuan/Hunyuan3D-2.1
- TripoSG 1.5B — VAST-AI, Jan 2026, MIT
- Stable Fast 3D — huggingface.co/stabilityai/stable-fast-3d (emergency fallback only)
- YOLOE-26 — successor to YOLO-World (+10 AP LVIS, 1.4× faster, Luxonis-supported)
- EfficientSAM3 — RepViT/TinyViT + MobileCLIP text encoder, ONNX+CoreML
- DepthAI v3 — docs.luxonis.com/software-v3/depthai/
- Rapier — github.com/dimforge/rapier
- MuJoCo — mujoco.readthedocs.io (v3.3.2+)
- CoACD — github.com/SarahWeiii/CoACD (`pip install coacd`)
- LTX-2-19B + IC-LoRA-Depth-Control — huggingface.co/Lightricks/LTX-2-19b-IC-LoRA-Depth-Control
- CogVideoX-Fun — github.com/aigc-apps/CogVideoX-Fun (safety-net only)
- PhysQuantAgent visual prompting — arXiv 2603.16958
- OpenUSD — openusd.org
- PhysGaussian / PhysTwin / PhysDreamer (context only, not used directly)

---

**End of document.** Schema, pipeline, and sponsor mapping are intended to be stable through H18. Anything not in this PRD is out of scope.
