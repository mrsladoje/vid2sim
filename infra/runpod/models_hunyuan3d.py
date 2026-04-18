"""Hunyuan3D 2.1 loader for the RunPod mesh-gen server.

Wraps Tencent's Hunyuan3D-2.1 shape DiT + Paint 2.1 PBR textures into a
single `generate(rgb_bytes, mask_bytes) -> glb_bytes` call, which is
exactly the contract the FastAPI `/mesh` endpoint expects.

We deliberately import heavy deps lazily so the uvicorn worker can boot
fast; the first `load()` call pays the model download + compile tax.

Reference: https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

logger = logging.getLogger("vid2sim.pod.hunyuan3d")

_HF_REPO = "tencent/Hunyuan3D-2.1"


class _Hunyuan3DHandle:
    """Handle returned by :func:`load`. The server calls `.generate()`."""

    def __init__(self, shape_pipe, paint_pipe):
        self.shape_pipe = shape_pipe
        self.paint_pipe = paint_pipe

    def generate(self, rgb_bytes: bytes, mask_bytes: bytes) -> bytes:
        from PIL import Image

        rgb = Image.open(io.BytesIO(rgb_bytes)).convert("RGB")
        mask = Image.open(io.BytesIO(mask_bytes)).convert("L")
        # Shape DiT: image → untextured mesh (trimesh.Trimesh).
        mesh = self.shape_pipe(
            image=rgb, mask=mask,
            num_inference_steps=30,
            guidance_scale=5.0,
            octree_resolution=256,
        )[0]
        # Paint 2.1: unwrap + PBR texture.
        mesh = self.paint_pipe(mesh=mesh, image=rgb)
        buf = io.BytesIO()
        mesh.export(buf, file_type="glb")
        return buf.getvalue()


def load(weights_dir: Path) -> _Hunyuan3DHandle:
    """Construct a handle ready for `generate()` calls."""
    import torch

    weights_dir = Path(weights_dir)
    # Respect an override if the user pre-cached weights elsewhere.
    cache = weights_dir / "hunyuan3d-2.1"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(weights_dir / "hf"))

    # Import paths for Hunyuan3D 2.1. We try a few known paths and, on
    # failure, re-raise with ALL errors concatenated so the real
    # missing dep is visible in the log (instead of being hidden
    # behind a misleading second ImportError).
    shape_errors: list[str] = []
    Hunyuan3DDiTFlowMatchingPipeline = None
    for mod_path, cls_name in (
        ("hy3dshape.pipelines", "Hunyuan3DDiTFlowMatchingPipeline"),
        ("hy3dshape",           "Hunyuan3DDiTFlowMatchingPipeline"),
        ("hy3dgen.shapegen",    "Hunyuan3DDiTFlowMatchingPipeline"),  # 2.0 legacy
    ):
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            Hunyuan3DDiTFlowMatchingPipeline = getattr(mod, cls_name)
            logger.info("hy3dshape pipeline found at %s", mod_path)
            break
        except Exception as exc:  # noqa: BLE001
            shape_errors.append(f"{mod_path}: {type(exc).__name__}: {exc}")
    if Hunyuan3DDiTFlowMatchingPipeline is None:
        raise ImportError(
            "could not import Hunyuan3DDiTFlowMatchingPipeline; tried:\n  "
            + "\n  ".join(shape_errors)
        )

    paint_errors: list[str] = []
    Hunyuan3DPaintPipeline = None
    for mod_path, cls_name in (
        ("hy3dpaint.textureGenPipeline", "Hunyuan3DPaintPipeline"),
        ("hy3dpaint",                    "Hunyuan3DPaintPipeline"),
        ("hy3dgen.texgen",               "Hunyuan3DPaintPipeline"),  # 2.0 legacy
    ):
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            Hunyuan3DPaintPipeline = getattr(mod, cls_name)
            logger.info("hy3dpaint pipeline found at %s", mod_path)
            break
        except Exception as exc:  # noqa: BLE001
            paint_errors.append(f"{mod_path}: {type(exc).__name__}: {exc}")
    if Hunyuan3DPaintPipeline is None:
        raise ImportError(
            "could not import Hunyuan3DPaintPipeline; tried:\n  "
            + "\n  ".join(paint_errors)
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    shape_pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        _HF_REPO, subfolder="hunyuan3d-dit-v2-1", cache_dir=str(cache),
        torch_dtype=dtype,
    ).to(device)
    paint_pipe = Hunyuan3DPaintPipeline.from_pretrained(
        _HF_REPO, subfolder="hunyuan3d-paintpbr-v2-1", cache_dir=str(cache),
    )
    logger.info("hunyuan3d pipelines loaded on %s (%s)", device, dtype)
    return _Hunyuan3DHandle(shape_pipe, paint_pipe)
