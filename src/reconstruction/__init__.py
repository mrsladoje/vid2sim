"""VID2SIM Stream 02 — Reconstruction.

PerceptionFrame bundle on disk  →  ReconstructedObject set on disk.

Bounded context. Nothing from DepthAI / camera internals leaks across this
boundary; we only read files written per `spec/perception_frame.md` and we
only write files per `spec/reconstructed_object.md`.
"""

__all__ = [
    "fusion",
    "backproject",
    "stub_emitter",
    "runpod_client",
    "sf3d_runner",
    "icp_align",
    "decimate",
    "vio",
    "pod_watchdog",
]
