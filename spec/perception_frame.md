# PerceptionFrame Bundle Specification v1.1

This specification defines the exact structure and format of the dataset emitted by Stream 1 (Perception) to be consumed downstream by Stream 2 (Reconstruction) and others.

This format provides an anti-corruption layer. Downstream contexts only parse these files and do not access the DepthAI or camera API directly.

**Status: v1.1 — segmentation invariants now mandatory (was optional in v1.0).**

## Bundle Validity Invariants (v1.1)

A bundle is **invalid** and MUST be rejected by downstream consumers if any of the following are violated:

1. **Per-object segmentation is mandatory.** At least one frame's `mask_track.png` MUST contain a non-zero pixel, and at least one frame's `objects.json` MUST contain at least one entry. A capture without tracked objects produces no `ReconstructedObject`s and is therefore unusable for Stream 02.
2. **`class_prompts` must reflect reality.** The labels in `capture_manifest.json::class_prompts` MUST match the open-vocab prompts passed to the segmenter at capture time, and SHOULD describe the actual scene contents.
3. **Frame integers monotonic + zero-padded.** Every frame must use the `XXXXX` 5-digit prefix and integers must form a contiguous range starting at `00000`.
4. **All declared per-frame files must exist.** Missing any of `rgb.jpg`, `depth.png`, `conf.png`, `mask_class.png`, `mask_track.png`, `pose.json`, `imu.jsonl`, `objects.json` for a present frame index is a hard error.

`pose.json` containing identity translation + identity quaternion is acceptable in v1.1 (VIO not yet online); downstream code falls back to stereo-only depth when poses are degenerate.

`src/perception/bundle.py::BundleReader.validate()` enforces these invariants — call it before consuming a bundle.

## Directory Structure

A valid PerceptionFrame bundle resides in a directory named `data/captures/<session_id>/` and must contain the following:

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

## `capture_manifest.json`

Describes the overall session metadata and limits.

```json
{
  "session_id": "string",
  "device_serial": "string",
  "firmware_version": "string",
  "capture_fps": 15,
  "frame_count": "integer",
  "class_prompts": ["chair", "table", "cup", "bottle"],
  "timebase_ns": "integer"
}
```

## `intrinsics.json`

Camera matrix and stereo baseline required for back-projection. Values are for the main RGB/depth aligned coordinate space.

```json
{
  "camera_matrix": [
    [800.0, 0.0, 960.0],
    [0.0, 800.0, 540.0],
    [0.0, 0.0, 1.0]
  ],
  "resolution": [1920, 1080],
  "baseline_m": 0.075
}
```

## `frames/` Files Format

Each timestep generates a set of synced files sharing an integer prefix `XXXXX` (0-padded to 5 digits).

*   **`XXXXX.rgb.jpg`**: 1080p (1920x1080) RGB image encoded as JPEG, quality 90.
*   **`XXXXX.depth.png`**: 16-bit uint PNG. Represents Z-depth in millimeters. `0` indicates invalid/missing data.
*   **`XXXXX.conf.png`**: 8-bit uint PNG. Represents LENS stereo confidence (0 = invalid, 255 = high confidence).
*   **`XXXXX.mask_class.png`**: 8-bit uint PNG. Pixel value corresponds to the index of the detected class from `capture_manifest.json`'s `class_prompts` array. `0` = background.
*   **`XXXXX.mask_track.png`**: 16-bit uint PNG. Pixel value corresponds to the active track ID of the object. `0` = background.

*   **`XXXXX.pose.json`**:
    ```json
    {
      "translation": [x, y, z],
      "rotation_quat": [qx, qy, qz, qw]
    }
    ```

*   **`XXXXX.imu.jsonl`**: JSON-lines formatted IMU records, containing raw BMI270 accelerometer/gyroscope readings within the frame's temporal window limit.
    ```json
    {"timestamp_ns": 123456789, "accel": [x, y, z], "gyro": [rx, ry, rz]}
    {"timestamp_ns": 123458999, "accel": [x, y, z], "gyro": [rx, ry, rz]}
    ```

*   **`XXXXX.objects.json`**: Extracted metadata per object for this frame. Let `N` be the number of tracked objects active in this frame.
    ```json
    [
      {
        "track_id": 1,
        "class": "chair",
        "bbox2d": [xmin, ymin, xmax, ymax],
        "bbox3d": {"center": [x, y, z], "size": [w, h, d]},
        "conf": 0.95
      }
    ]
    ```

## Timestamps & Sync

All measurements in a frame's prefix `XXXXX` are tightly synchronized. The `timebase_ns` provides the monotonic start-time of the session, and all subsequent timing uses this common referential.
