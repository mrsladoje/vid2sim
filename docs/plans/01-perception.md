# Stream 01 — Perception (Person 1)

> Bounded context: everything that runs on the **OAK-4 D Pro** edge device, plus the thin host-side ingestion process that receives its stream. Owner is responsible for getting calibrated, time-synchronised RGB + depth + mask + IMU off the camera and landing it on disk as a `PerceptionFrame` bundle.

See also: [`../PHASED_PLAN.md`](../PHASED_PLAN.md), [`../adr/ADR-002-hybrid-depth-fusion.md`](../adr/ADR-002-hybrid-depth-fusion.md), [`../adr/ADR-007-compute-split.md`](../adr/ADR-007-compute-split.md), [`../VID2SIM_PRD.md`](../VID2SIM_PRD.md) §7 Stage A, §5.

---

## 1. Scope & bounded context

**Owns**
- DepthAI v3 YAML pipeline definition (on-NPU nodes + host-node wiring).
- LENS neural stereo depth (on-device), NFOV mode.
- YOLOE-26 open-vocabulary segmentation (on-NPU; +10 AP LVIS vs YOLO-World, 1.4× faster, Luxonis-supported on OAK-4 RVC4), class list from a capture-time config file. Optional edge SAM via EfficientSAM3 (RepViT/TinyViT + MobileCLIP text encoder, ONNX+CoreML) — weights rolling out Q1 2026, bench at H0–H2.
- ObjectTracker 3D + SpatialLocationCalculator (on-NPU).
- IMU capture at native rate (BMI270, 400 Hz).
- Host-side capture script that receives the stream over USB-C and writes a `PerceptionFrame` bundle to disk.
- Camera intrinsics + extrinsics calibration export.
- Record/replay tooling so the rest of the team can work from `.rrd`/`.mcap`/PNG-dump fixtures without the physical camera.

**Does not own** (hand-off points)
- Monocular depth (DA3) — Person 2 (Reconstruction).
- RTAB-Map VIO on host — Person 2.
- Stereo+DA3 RANSAC fusion — Person 2.
- Anything downstream of per-object 2D mask + depth.

---

## 2. Ubiquitous language (Perception)

| Term | Meaning |
|---|---|
| **PerceptionFrame** | One synchronised timestep: RGB, stereo depth, confidence, class-id mask, object-id mask, per-object 3D bbox+track-id, camera pose, IMU sample. Emitted at ~15 FPS. |
| **Capture session** | A 5–15 s continuous recording producing N `PerceptionFrame`s + one `intrinsics.json` + one `capture_manifest.json`. |
| **NPU graph** | The DepthAI v3 node graph compiled to the camera's RVC4. |
| **Confidence mask** | Per-pixel uint8 from LENS (0 = invalid, 255 = high confidence). |
| **Track id** | Stable integer assigned by ObjectTracker 3D across frames for one physical object. |
| **LENS** | Luxonis neural stereo depth model running on the camera NPU. |
| **Class prompt set** | The list of open-vocabulary labels fed to YOLOE-26 at capture start (e.g. `["chair", "table", "cup", "bottle"]`). |
| **Capture manifest** | JSON header describing device serial, firmware, intrinsics, class prompts, timebase. |

---

## 3. External dependencies (consumed)

| From | What | Format |
|---|---|---|
| — | Hardware: OAK-4 D Pro over USB-C | — |
| Person 3 | Class prompt set for capture | `config/class_prompts.yaml` (list of strings) |
| Person 3 | `scene.json` schema frozen at G0 | `spec/scene.schema.json` — only consumed to know `PerceptionFrame` field names don't collide |

No runtime code dependency on other contexts. Perception is upstream of everything.

---

## 4. External deliverables (produced)

The **PerceptionFrame bundle** is this context's only published contract. Format is frozen at G0.

```
data/captures/<session_id>/
  capture_manifest.json    # device, intrinsics, class prompts, timebase, N frames
  intrinsics.json          # focal_px, cx, cy, resolution, baseline_m (stereo)
  frames/
    00000.rgb.jpg          # 1080p RGB, JPEG q=90
    00000.depth.png        # 16-bit PNG, millimetres, 0 = invalid
    00000.conf.png         # 8-bit PNG, 0..255
    00000.mask_class.png   # 8-bit PNG, class index
    00000.mask_track.png   # 16-bit PNG, track id
    00000.pose.json        # on-device camera pose estimate (may be identity for v1)
    00000.imu.jsonl        # 1 line per IMU sample in this frame window
    00000.objects.json     # [{track_id, class, bbox2d, bbox3d, conf}]
    ...
```

Consumers: Person 2 (Reconstruction) reads this bundle exclusively. Person 3 reads nothing from here directly; they read ReconstructedObjects produced by Person 2.

Anti-corruption layer: nothing from DepthAI internal types leaks. Everything is plain files + plain JSON.

---

## 5. Phased tasks

| Phase | Window | Task | Subtask | Artifact |
|---|---|---|---|---|
| G0 | H0–H2 | Bootstrap repo slice | Create `src/perception/` package, add `pytest` skeleton, wire CI stub | green CI on empty module |
| G0 | H0–H2 | Confirm camera hardware | Plug in; run `depthai-viewer`; verify LENS stream renders; note if it's S vs D Pro | `docs/perception/camera_check.md` (decision note) |
| G0 | H0–H2 | Freeze PerceptionFrame on-disk format with Person 2 | Draft spec in `spec/perception_frame.md`; walk through with Person 2; get signoff | `spec/perception_frame.md` v1.0 |
| **G0 gate** | H2 | Format frozen, camera alive | — | — |
| G1 | H2–H6 | Offline-replayable stub capture | Record 10 s using `depthai-viewer` default pipeline; convert to the bundle format with a converter script | `data/captures/stub_01/` |
| G1 | H2–H6 | DepthAI v3 pipeline YAML v1 | Nodes: ColorCamera, StereoDepth (LENS), YOLOE-26, ObjectTracker, SpatialLocationCalculator, IMU, XLinkOut for each | `src/perception/pipelines/capture_v1.yaml` |
| G1 | H2–H6 | Host ingest daemon | Python script subscribing to XLink queues, aligning timestamps, writing to bundle dir | `src/perception/capture.py` |
| G1 | H2–H6 | Intrinsics exporter | Pull calibration from device, emit `intrinsics.json` | `src/perception/calib.py` |
| **G1 gate** | H6 | End-to-end synthetic capture runs; Person 2 can read a bundle without Person 1 present | — | — |
| G2 | H6–H12 | Real capture of 1 hero object | Chair on venue table; 10 s at 15 FPS; YOLO prompt `["chair"]` | `data/captures/hero_01/` |
| G2 | H6–H12 | Mask quality triage | Compute per-frame mask IoU vs manual labels on 5 frames; if <0.6 adjust prompts | `tests/perception/test_mask_quality.py` |
| G2 | H6–H12 | IMU sanity check | Plot IMU trace; verify gravity aligned, no dropouts | `tests/perception/test_imu_sanity.py` |
| **G2 gate** | H12 | Real hero bundle exists; Person 2 confirms reconstruction ran end-to-end on it | — | — |
| G3 | H12–H18 | Full demo-scene capture | 3–5 objects on/near the venue table; class prompt set from Person 3 | `data/captures/demo_scene/` |
| G3 | H12–H18 | Redundant backup captures | Two independent captures of the same scene for demo-day safety | `data/captures/demo_scene_backup/` |
| G3 | H12–H18 | Record replay-only mode | Add `--replay <bundle>` flag that fakes the camera so the demo can run without hardware | `src/perception/replay.py` |
| **G3 gate** | H18 | Demo-scene bundle + backup bundle on disk; replay mode verified | — | — |
| G4 | H18–H22 | Polish + docs | README slice, run-book, capture recipe | `docs/perception/README.md` |
| G4 | H18–H22 | Tests to 80% on capture code | unit tests on converter + manifest schema | pytest coverage report |
| **G4 gate** | H22 | CI green, tests ≥80% on perception module, run-book reproducible | — | — |
| G5 | H22–H24 | Demo-day standby | Keep camera plugged, USB seated, replay bundle warm | — |

---

## 6. Phase gates

Each gate must be green before advancing. If red: follow the mitigation column.

| Gate | Automated check | Manual check | Artifact check | If red |
|---|---|---|---|---|
| G0 | `pytest src/perception -q` passes on empty skeleton; CI green | Camera enumerates via `depthai-viewer` | `spec/perception_frame.md` exists and signed by Person 2 | If camera is OAK-4 S not D Pro, log in `camera_check.md`, proceed with degraded-quality flag |
| G1 | Converter script produces a bundle that loads in Person 2's reader without error | Visual inspection of RGB/depth alignment in a notebook | `data/captures/stub_01/capture_manifest.json` validates against `spec/perception_frame.md` | Hand Person 2 a manually-crafted bundle so they are unblocked; fix ingest async |
| G2 | `test_mask_quality.py` ≥0.6 IoU on 5 sampled frames; `test_imu_sanity.py` green | Open bundle in `rerun` or equivalent and sanity-check alignment | `data/captures/hero_01/` has ≥100 frames, intrinsics, manifest | If mask IoU <0.6: widen prompt list, lower NMS threshold; if still fails, accept lower quality and flag to Person 3 |
| G3 | Replay mode reproduces a past bundle identically (hash match on a sampled frame) | Walk-through: plug in camera, record demo scene, bundle appears | Two full bundles + replay flag works offline | Use the stub bundle as demo material; flag loss to Queen |
| G4 | `pytest --cov=src/perception` ≥80% on converter + manifest modules; `ruff`, `black`, `mypy` clean | — | `docs/perception/README.md` present | Lower coverage target only with Queen approval |
| G5 | — | Dry-run capture works twice in a row in venue conditions | Backup bundle loaded and ready | Fall back to replay-only mode |

---

## 7. Risk & fallback (stream-specific)

| Risk | Likelihood | Fallback |
|---|---|---|
| Only OAK-4 S available, not D Pro | Medium | Accept: pipeline still runs, LENS unverified on S — flag in README, continue. Decision point H0. |
| LENS produces holes on glossy table | High | Expected — Person 2's DA3 fusion compensates. Ensure confidence mask is exported so Person 2 can trust-weight it. |
| YOLOE-26 drops objects between frames | Medium | ObjectTracker bridges gaps; if still losing tracks, relax confidence threshold and accept more false positives. |
| USB-C disconnect mid-capture | Low | Host ingest writes frames incrementally, not at end; a truncated bundle is still usable. |
| DepthAI v3 VSLAM host node unavailable | Medium | Don't use it from the perception side. Camera emits per-frame on-device pose estimate only; Person 2 owns real pose via RTAB-Map. |
| Thermal throttle during long capture | Low | Cap captures at 15 s. If stream drops below 10 FPS, abort and rerecord. |

---

## 8. Day-of-demo responsibilities

- Arrive early; plug in camera, run a warm-up capture, verify bundle.
- During pitch: on cue, run the live capture (or play replay bundle). Announce class prompts.
- If camera fails: switch to replay mode (one keystroke).
- Keep the backup bundle hot-loaded on an adjacent terminal.

---

## 9. Definition of done

- [ ] `spec/perception_frame.md` v1.0 frozen and signed off.
- [ ] DepthAI v3 pipeline YAML checked in, loads on the device, all nodes reachable.
- [ ] At least two real-scene bundles on disk (hero + demo).
- [ ] Replay mode verified against a pre-recorded bundle.
- [ ] Tests ≥80% on converter + manifest; CI green.
- [ ] Run-book (`docs/perception/README.md`) takes a fresh operator from zero to a valid bundle in ≤10 minutes.
