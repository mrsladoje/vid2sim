"""CLI entry point: read a PerceptionFrame bundle, emit a full demo
scene ReconstructedObject set.

Usage:
    python scripts/reconstruct_demo_scene.py \
        --capture data/captures/demo_scene \
        --session demo_scene \
        --config config/runpod.yaml

If `--config` points at a valid RunPod endpoint the pod is the mesh
generator. Otherwise a local synthetic generator is used (useful when
developing offline); provenance is stamped with `mesh_origin = "stub"`
in that case so Person 3 can see the gap.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from pathlib import Path

import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from perception.bundle import BundleInvariantError, BundleReader  # noqa: E402
from reconstruction.batch import reconstruct_session  # noqa: E402
from reconstruction.hero_orchestrator import ReconstructorConfig  # noqa: E402
from reconstruction.pod_watchdog import PodWatchdog  # noqa: E402
from reconstruction.runpod_client import RunPodClient, RunPodConfig  # noqa: E402
from reconstruction.sf3d_runner import SF3DRunner  # noqa: E402


def _local_box_client():
    """In-process mesh generator for offline dry runs.

    Emits a unit cube for every object so we can exercise the end-to-end
    pipeline without hitting the pod. The orchestrator's ICP then scales
    the cube to match the observed cloud — crude but honest for H0–H2.
    """
    from reconstruction.runpod_client import MeshCall

    class _Local:
        def __init__(self):
            buf = io.BytesIO()
            trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(buf, file_type="glb")
            self._glb = buf.getvalue()

        def generate_mesh(self, rgb, mask, *, model="hunyuan3d"):
            return MeshCall(
                glb_bytes=self._glb,
                mesh_origin_detail="stub",
                mesh_origin="identity",
                ran_on="stub",
                generation_s=0.0,
                pod_id="",
                attempts=0,
                error="offline dry-run",
            )

    return _Local()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--out", type=Path, default=Path("data/reconstructed"))
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--frame", type=int, default=0)
    parser.add_argument("--max-objects", type=int, default=5)
    parser.add_argument("--offline", action="store_true",
                        help="Skip RunPod; use local unit-cube emitter.")
    parser.add_argument("--skip-validation", action="store_true",
                        help="Bypass BundleReader.validate() — DANGEROUS, use only for debugging.")
    parser.add_argument("--model", default=None,
                        help="Override mesh model (sf3d | triposg | hunyuan3d). "
                             "Default: read client.primary_model from --config.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    # Per spec v1.1, fail fast if the bundle is missing per-object
    # segmentation rather than burn pod minutes on a doomed run.
    if not args.skip_validation:
        try:
            BundleReader(args.capture).validate()
            logging.info("Bundle %s passed v1.1 invariants", args.capture)
        except BundleInvariantError as exc:
            logging.error("Bundle invariant violation: %s", exc)
            logging.error("Fix the capture (re-run with --yolo-blob and "
                          "matching --prompts) or pass --skip-validation "
                          "to bypass this check.")
            return 4

    # Resolve primary model: CLI > yaml > ReconstructorConfig default.
    resolved_model = args.model
    rcfg = None
    if args.config is not None and not args.offline:
        rcfg = RunPodConfig.from_yaml(args.config)
        if resolved_model is None:
            resolved_model = rcfg.primary_model
    if resolved_model is None:
        resolved_model = "sf3d"  # safest default — fastest warm path
    logging.info("Mesh model: %s", resolved_model)
    cfg = ReconstructorConfig(out_root=args.out, primary_model=resolved_model)

    watchdog = None
    client_ctx = None
    if args.offline or args.config is None:
        client = _local_box_client()
    else:
        assert rcfg is not None
        if "REPLACE_ME" in rcfg.endpoint:
            logging.warning("config/runpod.yaml endpoint is a placeholder; "
                            "switching to offline stub emitter.")
            client = _local_box_client()
        else:
            api_key = os.environ.get("RUNPOD_API_KEY", "")
            if not api_key:
                logging.warning("RUNPOD_API_KEY not set; pod calls will "
                                "fail and watchdog will trip — fallback "
                                "path will be exercised.")
            sf3d = SF3DRunner()
            client_ctx = RunPodClient(rcfg, local_fallback=sf3d)
            client = client_ctx
            watchdog = PodWatchdog(client_ctx,
                                   failure_threshold=rcfg.failure_threshold)

    try:
        report = reconstruct_session(
            args.capture, args.session,
            runpod_client=client, watchdog=watchdog,
            frame=args.frame, max_objects=args.max_objects, cfg=cfg,
        )
    finally:
        if client_ctx is not None:
            client_ctx.close()

    print(json.dumps({
        "session_dir": str(report.session_dir),
        "total_objects": report.total_objects,
        "successes": report.successes,
        "wall_time_s": round(report.wall_time_s, 3),
        "per_object_s": [round(x, 3) for x in report.per_object_s],
        "mesh_origins": report.mesh_origins,
    }, indent=2))
    return 0 if report.successes else 1


if __name__ == "__main__":
    sys.exit(main())
