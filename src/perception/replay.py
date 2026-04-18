import argparse
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser("Perception Replay Mode")
    parser.add_argument("--bundle", required=True, help="Path to PerceptionFrame bundle")
    parser.add_argument("--fps", type=float, default=15.0, help="Target playback fps")
    return parser.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    
    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        logger.error(f"Bundle {bundle_path} does not exist.")
        return
        
    logger.info(f"Faking camera stream by replaying bundle from {bundle_path} at {args.fps} FPS")
    
    # In a real implementation we would stream these over XLinkIn nodes or 
    # mock the XLink queues in `capture.py`.
    # For now we acknowledge the replay logic stub.
    
    logger.info("Replay stream initialized and waiting for downstream consumers...")

if __name__ == "__main__":
    main()
