#!/usr/bin/env python3
"""Pretty-mode overnight render harness (skeleton).

Takes a sim replay (RGB + depth + optionally normals) and produces a
motion-preserved prettified video via LTX-2-19B + IC-LoRA-Depth-Control.
CogVideoX-Fun-V1.5-Control is kept as a known-to-boot MPS safety net.

This file is a harness scaffold landed at G1 (per plan §5). Swap in the
real model calls at G2 for the bench, then run the full pass at H16–H18
for overnight completion by G4.

Intentionally keeps the ML dependencies in TRY/EXCEPT so the scaffold is
importable and testable without the heavy weights installed.

Usage:
    python demo/render_pretty.py \\
        --replay-dir data/replays/demo_scene/ \\
        --out demo/demo_pretty.mp4 \\
        --model ltx2 \\
        --seconds 10
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Literal

ModelName = Literal["ltx2", "ltx2-fallback", "cogvideox-fun", "wan22-fun"]

MODEL_REGISTRY: dict[ModelName, str] = {
    # Primary: LTX-2-19B + IC-LoRA-Depth-Control (Lightricks, Mar 2026).
    "ltx2": "Lightricks/LTX-2-19b-IC-LoRA-Depth-Control",
    # Fallback: Lightricks/LTX-Video-ICLoRA-depth-13b-0.9.7.
    "ltx2-fallback": "Lightricks/LTX-Video-ICLoRA-depth-13b-0.9.7",
    # Safety net: CogVideoX-Fun-V1.5-Control. Known to boot on MPS.
    "cogvideox-fun": "alibaba-pai/CogVideoX-Fun-V1.5-Control",
    # Stretch: Wan 2.2 Fun Control GGUF (MPS support is flaky).
    "wan22-fun": "aigc-apps/Wan2.2-Fun-Control-GGUF",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--replay-dir",
        required=True,
        type=Path,
        help="Directory with per-frame rgb_xxxx.png and depth_xxxx.exr (or .npy).",
    )
    p.add_argument("--out", required=True, type=Path, help="Output .mp4 path.")
    p.add_argument(
        "--model",
        choices=list(MODEL_REGISTRY.keys()),
        default="ltx2",
        help="Pretty-mode backbone.",
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=10.0,
        help="Output clip duration. Budget: 30–90 s wall time per 1 s output.",
    )
    p.add_argument(
        "--prompt",
        type=str,
        default="a photorealistic living-room scene, cinematic lighting",
        help="Text prompt fed to the video-diffusion head.",
    )
    p.add_argument("--dry-run", action="store_true", help="Log plan only; skip model load.")
    return p.parse_args()


def ensure_replay_inputs(replay_dir: Path) -> None:
    if not replay_dir.exists():
        raise FileNotFoundError(f"replay dir not found: {replay_dir}")
    rgb = sorted(replay_dir.glob("rgb_*.png"))
    depth = sorted(replay_dir.glob("depth_*.npy")) + sorted(
        replay_dir.glob("depth_*.exr")
    )
    if not rgb:
        raise FileNotFoundError(f"no rgb_*.png frames in {replay_dir}")
    if not depth:
        raise FileNotFoundError(f"no depth_*.npy or depth_*.exr frames in {replay_dir}")
    if len(rgb) != len(depth):
        raise ValueError(
            f"frame count mismatch: {len(rgb)} rgb vs {len(depth)} depth"
        )


def render(args: argparse.Namespace) -> None:
    hf_id = MODEL_REGISTRY[args.model]
    ensure_replay_inputs(args.replay_dir)

    plan = {
        "model": args.model,
        "hf_id": hf_id,
        "replay_dir": str(args.replay_dir),
        "out": str(args.out),
        "seconds": args.seconds,
        "prompt": args.prompt,
    }
    print("[render_pretty] plan:", json.dumps(plan, indent=2))

    if args.dry_run:
        print("[render_pretty] --dry-run set, not loading model.")
        return

    t0 = time.time()
    try:
        # Real load goes here. Kept behind a try so the scaffold imports clean.
        import torch  # noqa: F401
        # from diffusers import LTX... (exact API depends on Lightricks release)
        raise NotImplementedError(
            "Pretty-mode loader is scaffold-only. Wire up the actual "
            "LTX-2 / CogVideoX pipeline at G2 bench time."
        )
    except ImportError as e:
        print(f"[render_pretty] dependencies missing: {e}", file=sys.stderr)
        sys.exit(2)
    except NotImplementedError as e:
        print(f"[render_pretty] {e}", file=sys.stderr)
        sys.exit(3)
    finally:
        print(f"[render_pretty] elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    render(parse_args())
