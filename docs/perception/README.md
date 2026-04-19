# Perception (Stream 1) — run-book

Captures RGB + stereo depth + confidence + IMU off an **OAK-4 D Pro** and
writes a `PerceptionFrame` bundle to disk (`spec/perception_frame.md`).
Person 2 (Reconstruction) reads only the bundle; nothing else leaks across
this boundary.

## Zero-to-bundle in ≤10 minutes

1. **Plug in the camera.** USB-C to the host; use USB 3 cable for 1080p/15.
2. **Install deps** (first time only):
   ```bash
   python -m pip install -e ".[perception]"
   python -m pip install pytest pytest-cov
   ```
   This pulls `depthai`, `depthai-nodes` (for the YOLOv8-Seg parser), and
   `opencv-python-headless`.
3. **Confirm the camera enumerates**:
   ```bash
   python -c "from src.perception.capture import smoke_test; smoke_test(seconds=3)"
   ```
   Expect `smoke_test: NN frames in 3.0s` with NN > 10.
4. **Run a capture** (zero-config — auto-downloads YOLOv8-Seg from the Luxonis Zoo):
   ```bash
   python -m src.perception.capture --outdir data/captures/hero_01 --duration 10
   ```
   First run downloads the model (~10 MB, cached after that). Logs end with
   `Wrote <N> frames to data/captures/hero_01` and `Capture invariant OK: M
   total tracked-object detections`. On USB 2 you should see 90–110 frames;
   on USB 3, closer to 150.

   Filter to specific COCO classes (defaults to a household whitelist):
   ```bash
   python -m src.perception.capture --outdir data/captures/hero_01 \
       --duration 10 --prompts chair bottle cup
   ```
   Pass `--prompts all` to keep every COCO-80 detection.
5. **Validate** against the spec:
   ```bash
   python -m pytest tests/perception -q
   ```
   All tests green = the bundle matches `spec/perception_frame.md`.

## What gets written

See `spec/perception_frame.md` (v1.0, frozen). Each frame is 8 files sharing
a `00000.*` prefix; there's one `capture_manifest.json` and one
`intrinsics.json` per bundle.

## Replay (no camera needed)

```bash
python -m src.perception.replay --bundle data/captures/hero_01 --fps 15
```

Prints one log line per second with frame shape. Use `--loop` for demo-day
standby and `--max-frames N` for quick tests.

## Per-instance segmentation

The default network is the Luxonis Zoo's
`luxonis/yolov8-instance-segmentation-nano:coco-512x288` model (auto-downloaded,
cached). Output is `ImgDetectionsExtended` carrying per-instance pixel
masks at 512×288, upsampled on the host to RGB resolution and stamped into
`mask_class.png` + `mask_track.png`.

`--prompts` is an opt-in COCO-80 whitelist. Default covers common indoor
hero objects: `chair`, `couch`, `dining table`, `bed`, `bottle`, `cup`,
`wine glass`, `bowl`, `vase`, `potted plant`, `tv`, `laptop`, `book`,
`teddy bear`. Detections in classes outside the whitelist are dropped
before being written. Pass `--prompts all` to keep every COCO class.

Class indices in `mask_class.png` are the COCO-80 label index + 1 (so
`bottle` → 40, `chair` → 57; 0 = background — see
`capture.py::COCO_80_CLASSES` for the full ordering). Track IDs come from
detection order inside a frame (simple placeholder until a proper
ObjectTracker is plumbed).

### Custom blobs (legacy bbox-rectangle path)

If you have a custom YOLO blob (e.g. a non-COCO model), pass it
explicitly. Mask output is bbox rectangles only — no per-instance pixel
masks — but the bundle is still spec-compliant.

```bash
python -m src.perception.capture --outdir data/captures/demo_scene \
    --duration 10 --prompts chair bottle cup \
    --yolo-blob models/my_custom.blob
```

## Stub generator (development without hardware)

```bash
python scripts/generate_perception_stub.py --outdir data/captures/stub_01 \
    --frames 150
```

Produces a synthetic bundle with the exact on-disk shape the camera writes
(1920x1080 RGB, 16-bit depth, 26 IMU samples/frame) so downstream streams
and CI can run without plugging in.

## Artifacts on disk

| Bundle | Purpose | Gate |
|---|---|---|
| `data/captures/stub_01/` | Synthetic stub, CI unblock | G1 |
| `data/captures/hero_01/` | Chair-only real capture | G2 |
| `data/captures/demo_scene/` | Full demo-scene capture | G3 |
| `data/captures/demo_scene_backup/` | Redundant demo-day safety net | G3 |

## Tests

```bash
python -m pytest tests/perception \
    --cov=src.perception.bundle --cov=src.perception.replay \
    --cov-report=term-missing --cov-fail-under=80 -q
```

The 80 % gate is enforced by `.github/workflows/perception-ci.yml`. CI runs
without `depthai` installed — the library is import-guarded in `bundle.py`
and `replay.py`; `capture.py` is exercised only on real hardware.

## Common failures

| Symptom | Fix |
|---|---|
| `No available devices (2 connected, but in use)` | Previous DepthAI handle still alive. Wait 2–3 s, rerun. |
| `setOutputSize is not supported on RVC4` | Already handled — depth is upsampled on the host. |
| `Host is reading IMU packets too slowly` | Bump `setBatchReportThreshold` in `_build_pipeline` (currently 20). |
| `USB connection speed: HIGH / USB2` | Cosmetic but halves fps — swap to USB 3 cable. |
