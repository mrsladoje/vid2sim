# ADR-007: Compute split — edge NPU for perception, M3 Max for offline

- **Status:** Accepted
- **Date:** 2026-04-18
- **Deciders:** VID2SIM core team
- **Area:** Compute placement / deployment topology

## Context

VID2SIM spans three compute locations: the OAK-4 D Pro's onboard 52 TOPS Qualcomm-based NPU, the MacBook Pro M3 Max (MPS / CoreML, 40-core GPU, 128 GB unified memory), and — in principle — cloud inference. Every workload must be placed somewhere, and the placement shapes both the pitch (Luxonis edge story) and the failure modes (venue network, USB-C bandwidth) (PRD §5, §6). The OAK-4 S variant also has a stereo pair per the Luxonis shop, but the pipeline is specced against the D Pro; see PRD §15 open question 1.

Not everything fits everywhere: Hunyuan3D and DA3 do not fit on the RVC4 NPU; SAM-2 is too large; conversely, heavy on-laptop perception would strand the Luxonis NPU and undermine the "edge camera matters" story.

## Decision

Split the pipeline cleanly between edge and laptop:

**On-device (OAK-4 D Pro, 52 TOPS NPU):**
- LENS neural stereo depth
- YOLO-World open-vocabulary segmentation
- ObjectTracker 3D
- SpatialLocationCalculator
- IMU capture

**Off-device (M3 Max, MPS / CoreML):**
- Depth Anything 3 (DA3METRIC-LARGE)
- RTAB-Map visual-inertial odometry
- Hunyuan3D 2.1 (primary) and SF3D (fallback)
- VLM physics inference call
- Scene assembly + exporters (`scene.json` → glTF/MJCF/USD/PyBullet)

**Not used:** cloud inference.

## Alternatives Considered

- **Everything on the camera.** Rejected: Hunyuan3D and DA3 don't fit on the RVC4 NPU; SAM-2 is too large. The edge cannot run the diffusion stage, full stop.
- **Everything on the laptop.** Rejected: loses the Luxonis "edge camera matters" pitch, wastes the 52 TOPS NPU, and moves perception latency onto USB-C — hurting both capture speed and the story.
- **Cloud inference for the heavy stages.** Rejected: venue network risk is unacceptable for a live demo, and adds a dependency we cannot control.

## Consequences

**Positive**
- Real-time perception at the edge is the Luxonis narrative — fully honest.
- Heavy offline compute (diffusion, VLM) sits where the memory and bandwidth live (M3 Max unified memory).
- Clear failure isolation: a laptop crash does not corrupt the edge pipeline and vice versa.

**Negative**
- Two codebases to maintain: a DepthAI pipeline definition on the camera and a Python host runtime on the laptop.
- USB-C / PoE transport is the bottleneck between the two; payload must be minimised (compressed depth, selective RGB frames, IMU at native rate).
- Debugging spans two runtimes with different logs and clocks.

**Neutral**
- The split matches the PRD's Stage A (perception) vs. Stage B–E (offline processing) boundaries; no architectural surprise.

## References

- PRD §5 (Hardware constraints)
- PRD §6 (System architecture)
- PRD §7 (Pipeline stages)
- Related: ADR-002 (LENS on edge + DA3 on laptop depends on this split), ADR-003 (Hunyuan3D on M3 Max), ADR-008 (excludes cloud / Isaac).
