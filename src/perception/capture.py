import argparse
import json
import logging
import os
import time
from pathlib import Path

# Try to import depthai, but don't fail if we are just linting or mocking
try:
    import depthai as dai # type: ignore
except ImportError:
    dai = None

logger = logging.getLogger(__name__)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("VID2SIM Perception Host Ingest Daemon")
    parser.add_argument("--pipeline", default="src/perception/pipelines/capture_v1.yaml", help="Path to pipeline YAML")
    parser.add_argument("--outdir", default="data/captures/latest", help="Output directory")
    parser.add_argument("--timeout", type=int, default=15, help="Capture timeout in seconds")
    return parser.parse_args()

def setup_outdir(outdir: str) -> None:
    path = Path(outdir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "frames").mkdir(exist_ok=True)

def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    logger.info(f"Starting host ingest daemon. Target output: {args.outdir}")

    setup_outdir(args.outdir)

    if dai is None:
        logger.error("depthai library not installed. Cannot run real capture.")
        return

    logger.info("Initializing DepthAI v3 pipeline from YAML is not fully supported in public Python API, this acts as placeholder.")
    pipeline = dai.Pipeline()
    # Adding a dummy camera node so the firmware doesn't crash from being empty
    cam_rgb = pipeline.create(dai.node.ColorCamera)
    # In a real setup, we'd load pipeline.load_yaml(args.pipeline) if available
    
    try:
        with dai.Device() as device:
            device.startPipeline(pipeline)
            logger.info(f"Connected to device: {device.getMxId()}")
            
            # Since this is an empty placeholder pipeline, we won't subscribe to queues yet.
            # In a real setup, we would do: q_rgb = device.getOutputQueue(name="rgb", ...)
            
            start_time = time.time()
            frame_idx = 0
            
            while time.time() - start_time < args.timeout:
                # Polling loops, write png/jpg arrays to args.outdir/frames/XXXXX.*
                time.sleep(0.1) # Simulate capturing frames
                frame_idx += 1
                
            logger.info(f"Capture finished. Simulated reading {frame_idx} frames.")
    except RuntimeError as e:
        logger.error(f"RuntimeError caught: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
