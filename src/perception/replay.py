"""Replay a previously-captured PerceptionFrame bundle.

Used when the camera is unavailable (CI, demo-day fallback, downstream
integration work). Yields `FrameRecord` objects at the target FPS using the
same type that `capture.run_capture` writes, so consumer code is identical.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Iterator, Optional

from .bundle import BundleReader, FrameRecord

logger = logging.getLogger(__name__)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser("Perception replay")
    p.add_argument("--bundle", required=True, help="Path to a PerceptionFrame bundle directory")
    p.add_argument("--fps", type=float, default=15.0, help="Target playback fps")
    p.add_argument("--loop", action="store_true", help="Loop instead of exiting at end")
    p.add_argument("--max-frames", type=int, default=0, help="Stop after N frames (0 = all)")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def iter_bundle(bundle: Path | str, fps: float = 15.0, loop: bool = False,
                max_frames: int = 0) -> Iterator[FrameRecord]:
    """Generator that yields FrameRecords paced to the requested FPS."""
    reader = BundleReader(bundle)
    if len(reader) == 0:
        raise RuntimeError(f"Bundle {bundle} contains no frames")
    period = 1.0 / max(fps, 1e-6)
    emitted = 0
    while True:
        t0 = time.time()
        for i in range(len(reader)):
            rec = reader.read(i)
            yield rec
            emitted += 1
            if max_frames and emitted >= max_frames:
                return
            # Pace to target FPS.
            due = t0 + (i + 1) * period
            wait = due - time.time()
            if wait > 0:
                time.sleep(wait)
        if not loop:
            return


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    bundle = Path(args.bundle)
    if not bundle.exists():
        logger.error("Bundle %s does not exist", bundle)
        return 2

    reader = BundleReader(bundle)
    logger.info("Replaying %s (%d frames, target %.1f fps, loop=%s)",
                bundle, len(reader), args.fps, args.loop)
    n = 0
    for rec in iter_bundle(bundle, fps=args.fps, loop=args.loop, max_frames=args.max_frames):
        n += 1
        if n == 1 or n % max(int(args.fps), 1) == 0:
            logger.info("frame %d rgb=%s depth=%s imu=%d objs=%d", rec.index,
                        rec.rgb.shape, rec.depth_mm.shape, len(rec.imu), len(rec.objects))
    logger.info("Replay done, yielded %d frames", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
