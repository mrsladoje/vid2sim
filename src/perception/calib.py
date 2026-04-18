import argparse
import json
import logging
from pathlib import Path

try:
    import depthai as dai  # type: ignore[import-not-found]
except ImportError:
    dai = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Extrator for OAK camera parameters")
    parser.add_argument("--outdir", default="data/captures/latest", help="Output directory")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting intrinsics extractor")
    
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out_file = outdir / "intrinsics.json"
    
    if dai is None:
        logger.warning("depthai not installed, mocking intrinsics output.")
        mock_data = {
            "camera_matrix": [
                [800.0, 0.0, 960.0],
                [0.0, 800.0, 540.0],
                [0.0, 0.0, 1.0]
            ],
            "resolution": [1920, 1080],
            "baseline_m": 0.075
        }
        with open(out_file, "w") as f:
            json.dump(mock_data, f, indent=2)
        logger.info(f"Wrote mocked intrinsics to {out_file}")
        return

    with dai.Device() as device:
        calib = device.readCalibration()
        matrix = calib.getCameraIntrinsics(dai.CameraBoardSocket.RGB)
        baseline = calib.getBaselineDistance() * 1e-2 # cm to m
        
        data = {
            "camera_matrix": matrix,
            "resolution": [1920, 1080],  # Assuming 1080p
            "baseline_m": baseline
        }
        
        with open(out_file, "w") as f:
            json.dump(data, f, indent=2)
            
        logger.info(f"Wrote real intrinsics to {out_file}")

if __name__ == "__main__":
    main()
