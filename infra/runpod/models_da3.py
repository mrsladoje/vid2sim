"""Depth Anything v3 (metric large) loader for the RunPod pod.

Serves DA3 from the same pod that hosts the mesh-gen models. The
laptop-side fusion code in src/reconstruction/fusion.py consumes the
returned depth map alongside the on-device LENS stereo depth.

Returns float32 metric depth (metres) as numpy `.npy` bytes — small
(~1 MB compressed for 1920x1080), parseable in one numpy call.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger("vid2sim.pod.da3")

# PRD ADR-002 calls the model `depth-anything/DA3METRIC-LARGE`. The
# concrete HF identifier has shifted with releases — we try a few.
_REPO_CANDIDATES = (
    "depth-anything/Depth-Anything-V3-Metric-Large-hf",
    "depth-anything/DA3METRIC-LARGE",
    "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf",  # v2 fallback
    "depth-anything/Depth-Anything-V2-Large-hf",  # relative-depth fallback
)


class _DA3Handle:
    def __init__(self, processor, model, device, dtype, repo_id):
        self.processor = processor
        self.model = model
        self.device = device
        self.dtype = dtype
        self.repo_id = repo_id

    def predict(self, rgb_bytes: bytes, target_size: tuple[int, int] | None = None) -> np.ndarray:
        """Return a (H, W) float32 depth map in metres.

        `target_size` is (W, H) — when provided, the depth is resized
        back to match the original RGB resolution. When None, returns
        the model's native output resolution.
        """
        import torch
        from PIL import Image

        rgb = Image.open(io.BytesIO(rgb_bytes)).convert("RGB")
        orig_size = rgb.size  # (W, H)

        inputs = self.processor(images=rgb, return_tensors="pt").to(self.device)
        # Diagnostics: confirm the processed input actually has signal.
        pv = inputs["pixel_values"]
        logger.info("DA3 input pixel_values shape=%s dtype=%s "
                    "min=%.3f max=%.3f mean=%.3f",
                    tuple(pv.shape), pv.dtype, float(pv.min()),
                    float(pv.max()), float(pv.mean()))

        # Pure fp32 forward — autocast triggers all-zero output on the
        # V2 Metric Indoor Large checkpoint (observed empirically).
        with torch.no_grad():
            outputs = self.model(**inputs)
        depth = outputs.predicted_depth  # (1, H, W) or (1, 1, H, W)
        if depth.dim() == 4:
            depth = depth.squeeze(1)
        depth = depth.squeeze(0).float().cpu().numpy().astype(np.float32)

        logger.info("DA3 raw depth range: %.4f .. %.4f (shape %s, mean %.4f)",
                    float(depth.min()), float(depth.max()), depth.shape,
                    float(depth.mean()))

        # Resize back to the input resolution (HF processors normally
        # downsample to ~518 on the long edge).
        size = target_size or orig_size
        if (depth.shape[1], depth.shape[0]) != size:
            from PIL import Image as _Img
            depth_img = _Img.fromarray(depth)
            depth_img = depth_img.resize(size, _Img.BILINEAR)
            depth = np.asarray(depth_img, dtype=np.float32)
        return depth


def load(weights_dir: Path) -> _DA3Handle:
    import torch
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    weights_dir = Path(weights_dir)
    cache = weights_dir / "da3"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(weights_dir / "hf"))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    last_exc = None
    for repo in _REPO_CANDIDATES:
        try:
            logger.info("trying DA3 repo: %s", repo)
            processor = AutoImageProcessor.from_pretrained(repo, cache_dir=str(cache))
            # Load weights in fp32 so we don't trip a known underflow in
            # the metric-large checkpoint when the model is held in fp16
            # AND the input is also fp16. Autocast in `predict()` still
            # gives us fp16 throughput on the forward pass.
            model = AutoModelForDepthEstimation.from_pretrained(
                repo, cache_dir=str(cache),
            )
            model = model.to(device)
            model.eval()
            logger.info("DA3 loaded from %s on %s (autocast=%s)", repo, device, dtype)
            return _DA3Handle(processor, model, device=device, dtype=dtype,
                              repo_id=repo)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("DA3 repo %s failed: %s", repo, exc)
            continue

    raise RuntimeError(f"could not load any DA3 candidate; last error: {last_exc}")
