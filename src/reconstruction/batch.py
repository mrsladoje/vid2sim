"""Batch driver for a full demo scene (plan §G3).

Walks every object referenced in a PerceptionFrame capture's
`XXXXX.objects.json` (on the chosen keyframe), reconstructs each via
the hero orchestrator, and emits a session-level `reconstructed.json`
+ `world_pose.json` for Stream 03.

Intentionally sequential: the RunPod pod handles request serialisation
on its side. Parallel dispatch is easy to add via `concurrent.futures`
but it risks slamming the pod with cold-reload tax on every slot.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .hero_orchestrator import (
    ReconstructorConfig,
    reconstruct_one_object,
    write_session_index,
)
from .pod_watchdog import PodWatchdog
from .runpod_client import RunPodClient
from .vio import WorldPose, world_pose

logger = logging.getLogger(__name__)


@dataclass
class BatchReport:
    session_dir: Path
    total_objects: int
    successes: int
    wall_time_s: float
    per_object_s: list[float]
    mesh_origins: list[str]


def reconstruct_session(
    capture_dir: Path,
    session_id: str,
    *,
    runpod_client: RunPodClient,
    watchdog: Optional[PodWatchdog] = None,
    da3_fn=None,
    frame: int = 0,
    max_objects: int = 5,
    cfg: Optional[ReconstructorConfig] = None,
) -> BatchReport:
    cfg = cfg or ReconstructorConfig()

    objects_meta_path = capture_dir / "frames" / f"{frame:05d}.objects.json"
    if not objects_meta_path.exists():
        raise FileNotFoundError(f"no objects meta at {objects_meta_path}")
    objects_meta = json.loads(objects_meta_path.read_text())[:max_objects]

    world: WorldPose = world_pose(capture_dir, prefer_vio=True)

    if watchdog is not None:
        watchdog.check_once()  # one probe before we start
        if watchdog.has_tripped():
            logger.warning("starting batch while pod is tripped; expect SF3D fallback")

    t0 = time.monotonic()
    per_object_s: list[float] = []
    mesh_origins: list[str] = []
    emitted: list[tuple[int, str, Path]] = []

    for meta in objects_meta:
        track_id = int(meta["track_id"])
        class_name = "".join(c if c.isalnum() or c in ("_", "-") else "_"
                             for c in str(meta["class"]))
        bbox2d = meta["bbox2d"]
        t_obj = time.monotonic()
        try:
            obj_dir = reconstruct_one_object(
                capture_dir, session_id, frame=frame,
                track_id=track_id, class_name=class_name,
                bbox2d=bbox2d,
                runpod_client=runpod_client,
                da3_fn=da3_fn, world=world, cfg=cfg,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("object %s failed: %s", track_id, exc)
            continue

        manifest = json.loads((obj_dir / "object_manifest.json").read_text())
        mesh_origins.append(manifest["provenance"]["mesh_origin"])
        per_object_s.append(time.monotonic() - t_obj)
        emitted.append((track_id, class_name, obj_dir))

        if watchdog is not None:
            # Poll once after each object so long batches can still
            # notice a mid-run pod outage.
            watchdog.check_once()

    session_dir = write_session_index(
        session_id, emitted, world, out_root=cfg.out_root
    )

    return BatchReport(
        session_dir=session_dir,
        total_objects=len(objects_meta),
        successes=len(emitted),
        wall_time_s=time.monotonic() - t0,
        per_object_s=per_object_s,
        mesh_origins=mesh_origins,
    )
