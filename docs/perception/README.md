# Perception (Stream 1)

This module is responsible for capturing RGB, stereo depth, masks, and IMU from an OAK-4 D Pro camera, writing the output as a `PerceptionFrame` bundle to disk to be processed offline.

## Hardware Setup
1. Plug in the OAK-4 camera via USB-C or PoE.
2. Ensure you have the `depthai` Python library installed (`pip install depthai`).

## Running a Capture
```bash
python -m src.perception.capture --outdir data/captures/latest --timeout 15
```

This connects to the DepthAI v3 pipeline and runs the capture for 15 seconds.

## Replay Mode
To run without the physical camera (e.g. during a demo or tests):
```bash
python -m src.perception.replay --bundle data/captures/stub_01
```

## Running Tests
Run the pytest suite:
```bash
pytest tests/perception --cov=src/perception
```

## Creating Stubs
If you don't have a camera and just need to unblock Stream 2:
```bash
python scripts/generate_perception_stub.py
```
