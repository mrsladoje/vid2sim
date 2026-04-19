"""Depth Anything 3 loader for the RunPod pod.

DA3 is the ByteDance-Seed depth foundation model (released Nov 2025;
SOTA on monocular depth + camera pose). It ships its own `depth_anything_3`
Python package — NOT a HuggingFace `transformers` model. Use:

    from depth_anything_3.api import DepthAnything3
    model = DepthAnything3.from_pretrained("depth-anything/DA3MONO-LARGE")
    model = model.to("cuda")
    pred = model.inference(images=[pil_image])
    depth = pred.depth  # [N, H, W] float32 (relative; fuse to metric via stereo)

Returns the per-frame depth as numpy `.npy` bytes (float32 HxW).

Model choice — DA3MONO-LARGE (0.35B):
  - Monocular, fast, single-image input → matches our pipeline shape.
  - Output is **relative** depth — our RANSAC fusion in
    src/reconstruction/fusion.py aligns it to stereo metric scale.
  - Heavier alternatives (DA3-LARGE-1.1, DA3NESTED-GIANT-LARGE-1.1)
    are listed as fallbacks in case MONO is unavailable.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger("vid2sim.pod.da3")

# Repo IDs ranked by speed→quality. Monocular variant first since
# that's what fits our single-image-per-frame pipeline.
_REPO_CANDIDATES = (
    "depth-anything/DA3MONO-LARGE",
    "depth-anything/DA3-LARGE-1.1",
    "depth-anything/DA3-LARGE",
    "depth-anything/DA3-BASE",
)


class _DA3Handle:
    def __init__(self, model, device, repo_id):
        self.model = model
        self.device = device
        self.repo_id = repo_id

    def predict(self, rgb_bytes: bytes, target_size: tuple[int, int] | None = None) -> np.ndarray:
        """Return a (H, W) float32 depth map (relative — fuse to metric via stereo)."""
        import torch
        from PIL import Image

        rgb = Image.open(io.BytesIO(rgb_bytes)).convert("RGB")
        orig_size = rgb.size  # (W, H)

        with torch.no_grad():
            pred = self.model.inference(images=[rgb])

        # `pred.depth` shape is [N, H, W] float32. We send one image so N=1.
        depth = pred.depth
        if hasattr(depth, "cpu"):
            depth = depth.cpu().numpy()
        depth = np.asarray(depth, dtype=np.float32)
        if depth.ndim == 3:
            depth = depth[0]
        elif depth.ndim == 4:
            depth = depth[0, 0]

        logger.info("DA3 raw depth range: %.4f .. %.4f (shape %s, mean %.4f)",
                    float(depth.min()), float(depth.max()), depth.shape,
                    float(depth.mean()))

        size = target_size or orig_size
        if (depth.shape[1], depth.shape[0]) != size:
            from PIL import Image as _Img
            depth_img = _Img.fromarray(depth)
            depth_img = depth_img.resize(size, _Img.BILINEAR)
            depth = np.asarray(depth_img, dtype=np.float32)
        return depth


def load(weights_dir: Path) -> _DA3Handle:
    import torch

    weights_dir = Path(weights_dir)
    cache = weights_dir / "da3"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(weights_dir / "hf"))

    # `depth_anything_3` is the ByteDance-Seed package, installed via
    # `pip install -e` on the cloned repo (see pod_bootstrap.sh step 4).
    try:
        from depth_anything_3.api import DepthAnything3
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "depth_anything_3 not installed. Clone "
            "https://github.com/ByteDance-Seed/Depth-Anything-3 "
            "and `pip install -e .` it into the pod's venv."
        ) from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    last_exc = None
    for repo in _REPO_CANDIDATES:
        try:
            logger.info("trying DA3 repo: %s", repo)
            model = DepthAnything3.from_pretrained(repo)
            model = model.to(device=device)
            if hasattr(model, "eval"):
                model.eval()
            logger.info("DA3 loaded from %s on %s", repo, device)
            return _DA3Handle(model, device=device, repo_id=repo)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("DA3 repo %s failed: %s", repo, exc)
            continue

    raise RuntimeError(f"could not load any DA3 candidate; last error: {last_exc}")
