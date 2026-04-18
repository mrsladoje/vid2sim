# Camera Hardware Check (Phase G0)

**Date**: 2026-04-18
**Operator**: xLukus

## Device enumerated

| Field | Value |
|---|---|
| Product | `OAK4-D-PRO-AF` |
| Name | `OAK4-D-PRO` |
| Platform | `RVC4` |
| Device serial (MxId) | `3263741241` |
| Board | `NG9498-ASM` |
| EEPROM version | `7` |
| Connected cameras | `CAM_A` (RGB), `CAM_B` (left mono), `CAM_C` (right mono) |
| Stereo baseline | `0.075 m` (from calibration) |
| IMU | BMI270 available (IMU-to-camera extrinsics present in calibration) |

Pulled from `depthai==3.5.0` via `dai.Device.getDeviceName/Product/Platform/readCalibration()`.

## Smoke test

Ran a 3-second `Camera(CAM_A) → requestOutput(1920×1080, BGR888i, 15 fps)` pipeline:

- 18 frames received, shape `(1080, 1920, 3)` `uint8`, device timestamps monotonic.
- No device reset or firmware errors.

USB link reported `UsbSpeed.HIGH` (USB 2). For venue demos, use the supplied USB 3 cable to avoid the `Performance may be degraded` warning.

## Decisions locked at G0

- Hardware is the D Pro variant; no degraded-quality flag is needed.
- LENS neural stereo will be wired in at G1; the fallback for RVC4 if LENS graph is unavailable is `StereoDepth` with `PresetMode.ROBOTICS`, which still emits depth + confidence at 15 fps.
- YOLOE-26 blob is a separately-downloaded artifact. Capture runs without a blob write zero-valued class/track masks and log a warning; downstream consumers treat mask id 0 as background.

## Reproducing this check

```bash
python -m src.perception.calib --outdir data/captures/latest   # writes intrinsics.json + device_info.json
python -c "from src.perception.capture import smoke_test; smoke_test(seconds=3)"
```
