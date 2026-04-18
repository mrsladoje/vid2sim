# VID2SIM — Phased Implementation Plan (Index)

> Index only. Each of the 4 humans has a detailed subplan under [`plans/`](plans/). Product context: [`VID2SIM_PRD.md`](VID2SIM_PRD.md). Architecture decisions: [`adr/README.md`](adr/README.md).

## Project summary

VID2SIM turns a 5–15 s RGB-D capture from an **OAK-4 D Pro** into a **browser-playable, physics-ready 3D scene** in under 90 s of offline compute on an M3 Max. The pipeline is: on-device perception (LENS + YOLO-World + IMU) → host fusion (stereo + DA3METRIC-LARGE) + VIO → per-object completion (Hunyuan3D 2.1) + VLM physics properties (Claude Opus 4.7) → the single published contract `scene.json` → exporters (glTF+sidecar / MJCF / PyBullet / USD) → a static Three.js + Rapier WASM viewer. The 24-hour build is split across **4 bounded contexts** with **1 hard schema freeze at H2** and **5 global phase gates**.

## Bounded-context diagram

```mermaid
flowchart LR
  subgraph P1["Person 1 · Perception"]
    P1A[OAK-4 D Pro · LENS · YOLO-World · IMU]
  end
  subgraph P2["Person 2 · Reconstruction"]
    P2A[DA3 + RANSAC fusion · RTAB-Map VIO · Hunyuan3D/SF3D · ICP align]
  end
  subgraph P3["Person 3 · Scene Assembly (schema owner)"]
    P3A[VLM physics · V-HACD · Assembler · Exporters]
  end
  subgraph P4["Person 4 · Presentation"]
    P4A[Three.js+Rapier viewer · Choreography · Pretty-mode · Deck]
  end

  P1A -- "PerceptionFrame bundle<br/>(files + manifest.json)" --> P2A
  P2A -- "ReconstructedObject set<br/>(mesh.glb + manifest.json)" --> P3A
  P3A -- "SceneSpec<br/>(scene.json + scene.glb + sidecar)" --> P4A
  P3A -.schema v1.0 (spec/scene.schema.json).-> P4A
  P3A -.schema fields.-> P2A
  P3A -.class prompts.-> P1A
```

The three published contracts — **PerceptionFrame**, **ReconstructedObject**, **SceneSpec** — are the **only** way contexts talk. No context imports another's internals. Anti-corruption layers are file-on-disk + JSON.

## Ubiquitous language (shared glossary)

| Term | Meaning |
|---|---|
| **PerceptionFrame** | One synchronised edge-capture timestep (RGB + stereo depth + confidence + class/track masks + IMU + on-device pose). |
| **Capture session** | A 5–15 s bundle of N PerceptionFrames plus a manifest. |
| **Fused depth** | Per-frame RANSAC-aligned combination of stereo and DA3 monocular depth. |
| **World frame** | Single coordinate frame, +Y up, origin = first VIO keyframe, metres. |
| **Object point cloud** | Per-track world-frame 3D points produced by back-projecting masked fused depth. |
| **Raw mesh** | Watertight image-to-3D output in unit cube, UV + PBR. |
| **Aligned mesh** | Raw mesh after ICP scale+pose alignment to its object point cloud. |
| **ReconstructedObject** | One object's published bundle: mesh.glb + crop.jpg + manifest (class, transform, provenance). |
| **Scene object** | One entry in `scene.json.objects[]`. |
| **SceneSpec** | The `scene.json` file + its mesh directory (schema-versioned contract). |
| **Physics block** | `{mass_kg, friction, restitution, is_rigid}` per scene object. |
| **Convex decomposition** | N-hulls collision proxy for a dynamic rigid body (V-HACD). |
| **Sidecar physics JSON** | `scene.glb.physics.json` — avoids unratified `KHR_physics_rigid_bodies`. |
| **Provenance** | Origin tags per artifact: `depth_origin`, `pose_origin`, `mesh_origin`, `physics_origin`. |
| **Lookup table** | Class → default physics block; VLM fallback. |
| **Pretty mode** | Pre-rendered overnight video prettification via CogVideoX-Fun; off critical path. |
| **Choreography** | The 90-s scripted pitch interaction sequence. |
| **Kill-switch clip** | Backup demo video played if live demo fails. |
| **Gate (G0–G5)** | Global synchronisation point where all 4 streams check in. |

## Global timeline

| Window | G | Perception (P1) | Reconstruction (P2) | Scene (P3) | Presentation (P4) |
|---|---|---|---|---|---|
| H0–H2 | **G0** | Hardware alive; PerceptionFrame format drafted | DA3 + Hunyuan3D bench logged; RecObj contract drafted | **scene.schema.json v1.0 FROZEN**; example fixture published | Viewer boot; renders example fixture with physics |
| H2–H6 | **G1** | Stub capture bundle on disk; pipeline YAML v1 | Fusion + backproject + stub RecObj emitter | Assembler v0 on stubs; glTF+sidecar + MJCF exporters | All 4 interaction modes; stub scene loads |
| H6–H12 | **G2** | Hero object capture (`hero_01`) | Hero RecObj end-to-end: fused depth → Hunyuan3D → ICP → mesh.glb | VLM + V-HACD + ground plane; hero scene.json + exports | Hero scene interactive; deck draft; pretty bench |
| H12–H18 | **G3** | Demo scene + backup bundles; replay mode | Full demo scene RecObjs; thermal watchdog | Full demo `scene.json` + 3–4 exporters | Full demo scene at 60 FPS; choreography rehearsed; backup video |
| H18–H22 | **G4** | Run-book + 80% coverage on converter | 80% coverage on fusion + ICP; CI green | 80% coverage on exporters; schema docs | Pretty-mode overnight render; 2 dry-runs; deploy viewer |
| H22–H24 | **G5** | Demo standby | Demo standby | Demo standby | Final rehearsal; kill-switch primed |

**Hard rule:** no new features after H18 (G3). Integration-only after that.

## Pointers to detailed subplans

| # | Person | Bounded context | One-line scope | Plan |
|---|---|---|---|---|
| 1 | Person 1 | **Perception** | OAK-4 D Pro on-device pipeline → PerceptionFrame bundle on disk | [`plans/01-perception.md`](plans/01-perception.md) |
| 2 | Person 2 | **Reconstruction** | PerceptionFrame → fused depth + VIO + Hunyuan3D + ICP → ReconstructedObject set | [`plans/02-reconstruction.md`](plans/02-reconstruction.md) |
| 3 | Person 3 | **Scene Assembly** | Schema owner. ReconstructedObject → `scene.json` + glTF/MJCF/PyBullet/USD exporters | [`plans/03-scene-assembly.md`](plans/03-scene-assembly.md) |
| 4 | Person 4 | **Presentation** | Three.js + Rapier viewer + choreography + pretty-mode + pitch deck | [`plans/04-presentation.md`](plans/04-presentation.md) |

## Cross-team contracts

| # | Producer | Consumer | Artifact | Location | Schema source |
|---|---|---|---|---|---|
| C1 | P1 | P2 | **PerceptionFrame bundle** (RGB/depth/conf/mask/IMU/objects per frame + manifest) | `data/captures/<id>/` | `spec/perception_frame.md` (frozen at G0) |
| C2 | P2 | P3 | **ReconstructedObject set** (mesh.glb + crop + manifest per track) | `data/reconstructed/<id>/` | `spec/reconstructed_object.md` (frozen at G0) |
| C3 | P3 | P4 | **SceneSpec** (`scene.json` + `scene.glb` + sidecar physics JSON) | `data/scenes/<id>/` | **`spec/scene.schema.json` v1.0 (FROZEN at G0 — owned by P3)** |
| C4 | P3 | P1 | Class prompt set | `config/class_prompts.yaml` | list of strings |
| C5 | P3 | all | `spec/scene.example.json` | hand-crafted 3-object fixture | conforms to C3 schema |

**Rule:** the three schema-backed contracts (C1, C2, C3) are **additive-only after G1 (H6)**. Breaking changes after H6 require Queen signoff + notification to every stream. C3 is additionally **frozen at G0 (H2)** because Person 4 is coding against it from H2 onwards.

## Global phase gates

Every stream must meet its row of each gate before the team advances. Gates are the only synchronisation points; between them streams work independently on files.

### G0 — H2 · Foundation

- **Blocks all stream-specific work until green.**
- **P1**: camera enumerates; PerceptionFrame format draft; confirm S vs D Pro.
- **P2**: DA3 and Hunyuan3D bench numbers logged; RecObj contract drafted; MPS env stable.
- **P3**: **`spec/scene.schema.json` v1.0 is frozen**, `scene.example.json` validates, signoff from P1/P2/P4.
- **P4**: viewer skeleton builds; renders `scene.example.json` with Three.js + Rapier in-browser.
- **Global**: CI green on empty skeletons; repo scaffolding (src/, tests/, spec/, data/, docs/, web/) merged.

### G1 — H6 · Fake-data MVP, end-to-end smoke test

- **P1**: stub capture bundle on disk; P2 can read it without P1 present.
- **P2**: stub ReconstructedObject set on disk (primitive fakes ok); P3 can assemble a scene from it.
- **P3**: `scene.json` + `scene.glb` + sidecar produced from P2's stubs; MJCF exporter works on fixture.
- **P4**: viewer loads P3's stub scene with all 4 interaction modes.
- **Global**: an **integration smoke test** runs end-to-end on stub data (hook `scripts/smoke.sh`).

### G2 — H12 · Real hero object, end-to-end

- **P1**: `data/captures/hero_01/` exists with mask quality ≥0.6 IoU.
- **P2**: `data/reconstructed/hero_01/` has a correctly-scaled, world-posed, watertight mesh with full provenance.
- **P3**: `data/scenes/hero_01/` emitted; VLM + lookup both wired; V-HACD active.
- **P4**: hero scene loads in viewer; deck draft exists; pretty-mode bench number logged.
- **Global**: Hunyuan3D MPS budget decision locked (H10): primary = Hunyuan3D or primary = SF3D.

### G3 — H18 · Full demo scene; FEATURE FREEZE

- **P1**: demo scene + backup bundle + replay mode verified.
- **P2**: `data/reconstructed/demo_scene/` with 3–5 objects, provenance clean.
- **P3**: full `scene.json` + glTF/MJCF/PyBullet (+USD stretch) exports complete.
- **P4**: full scene at 60 FPS; choreography rehearsed; `backup_demo.mp4` recorded.
- **Global**: **no new features after this point**. Integration-only.

### G4 — H22 · Polish, coverage, pretty-mode, CI green

- **P1**: run-book; converter tests ≥80%.
- **P2**: fusion + ICP tests ≥80% (PRD NFR).
- **P3**: exporter tests ≥80% (PRD NFR); schema docs.
- **P4**: pretty-mode video rendered (if overnight permits); 2 dry-runs done; viewer deployed.
- **Global**: CI all green, lint all green, `mypy` clean.

### G5 — H24 · Demo-ready

- **P1**: camera hot, replay bundle warm.
- **P2**: reconstruction cached, models pre-warmed.
- **P3**: demo scene staged; backup scene ready.
- **P4**: pitch deck final, backup demo video primed, kill-switch tested.
- **Global**: one final full dress rehearsal done; fallback video proven playable.
