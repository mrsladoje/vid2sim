"""T-60 min pod pre-warm ritual (ADR-009 §operational run-book).

Usage (inside the pod, or from the laptop via `runpod exec`):
    python prewarm.py --weights /workspace/weights

Effect: loads both Hunyuan3D 2.1 and TripoSG 1.5B into GPU memory and
runs one inference each on a cached crop so the first real /mesh request
doesn't pay the cold-start tax.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger("vid2sim.pod.prewarm")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _warmup(weights_dir: Path, crop_path: Path, mask_path: Path) -> None:
    rgb = crop_path.read_bytes()
    mask = mask_path.read_bytes()
    for model in ("hunyuan3d", "triposg"):
        t0 = time.monotonic()
        if model == "hunyuan3d":
            from models_hunyuan3d import load  # type: ignore
        else:
            from models_triposg import load  # type: ignore
        handle = load(weights_dir)
        _ = handle.generate(rgb, mask)  # type: ignore[attr-defined]
        logger.info("warmed %s in %.2fs", model, time.monotonic() - t0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=Path, default=Path("/workspace/weights"))
    parser.add_argument("--crop", type=Path, default=Path("/workspace/warmup/crop.jpg"))
    parser.add_argument("--mask", type=Path, default=Path("/workspace/warmup/mask.png"))
    args = parser.parse_args()

    if not args.crop.exists() or not args.mask.exists():
        logger.error("cached warm-up crop missing: %s / %s", args.crop, args.mask)
        return 2

    _warmup(args.weights, args.crop, args.mask)
    return 0


if __name__ == "__main__":
    sys.exit(main())
