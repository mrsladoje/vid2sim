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
    """Handle returned by :func:`load`. The server calls `.generate()`.

    The Paint pipeline is optional: if it failed to import (e.g. because
    `bpy` — Blender's Python API — couldn't be installed), we still
    serve the Shape DiT's untextured mesh. For VID2SIM physics that is
    sufficient; the downstream pipeline only relies on geometry.
    """

    def __init__(self, shape_pipe, paint_pipe):
        self.shape_pipe = shape_pipe
        self.paint_pipe = paint_pipe  # may be None

    def generate(self, rgb_bytes: bytes, mask_bytes: bytes) -> bytes:
        from PIL import Image

        # Hunyuan3D-2.1's shape DiT expects an RGBA image whose alpha
        # channel is the object mask. If the source image already has
        # a real alpha channel (e.g. demo.png ships RGBA with correct
        # object cutout), use that — it beats any mask we might layer
        # on top. Otherwise, fall back to the mask the caller provided.
        src = Image.open(io.BytesIO(rgb_bytes))
        has_real_alpha = False
        if src.mode == "RGBA":
            a = src.split()[3]
            # "real" = non-trivial alpha, i.e. not every pixel fully
            # opaque. A uniform 255 alpha carries no information.
            mn, mx = a.getextrema()
            has_real_alpha = not (mn == mx == 255)

        if has_real_alpha:
            rgba = src.convert("RGBA")
        else:
            rgba = src.convert("RGB").convert("RGBA")
            mask = Image.open(io.BytesIO(mask_bytes)).convert("L")
            if mask.size != rgba.size:
                mask = mask.resize(rgba.size, Image.LANCZOS)
            rgba.putalpha(mask)

        # The pipeline's __call__ takes just `image=` in the reference
        # demos. Extra kwargs (num_inference_steps, octree_resolution,
        # guidance_scale, mask=) are not part of the public API and get
        # silently ignored. Stay minimal.
        mesh = self.shape_pipe(image=rgba)[0]

        # Paint 2.1: unwrap + PBR texture — only if available.
        if self.paint_pipe is not None:
            try:
                mesh = self.paint_pipe(mesh=mesh, image=rgba)
            except Exception as exc:  # noqa: BLE001
                logger.warning("paint pipeline failed at runtime (%s); "
                               "returning untextured shape mesh", exc)
        else:
            # Paint not loaded (usually because bpy won't import) —
            # bake a cheap image-projection vertex colour so the glb is
            # not flat grey. Runs in ~0.1 s, numpy only.
            _apply_projection_colors(mesh, rgba)

        buf = io.BytesIO()
        mesh.export(buf, file_type="glb")
        return buf.getvalue()


def _apply_projection_colors(mesh, rgba_image) -> None:
    """Fast per-vertex coloring by planar XY projection of the input
    image. Back-facing vertices are darkened so the rear of the mesh
    does not mirror the front photo."""
    import numpy as np
    import trimesh

    img = np.asarray(rgba_image.convert("RGB"), dtype=np.uint8)
    h, w = img.shape[:2]
    v = np.asarray(mesh.vertices, dtype=np.float32)
    if v.size == 0:
        return
    u = (v[:, 0] - v[:, 0].min()) / (v[:, 0].max() - v[:, 0].min() + 1e-9)
    y = (v[:, 1] - v[:, 1].min()) / (v[:, 1].max() - v[:, 1].min() + 1e-9)
    px = np.clip((u * (w - 1)).astype(np.int32), 0, w - 1)
    py = np.clip(((1.0 - y) * (h - 1)).astype(np.int32), 0, h - 1)
    colors = img[py, px].copy()
    try:
        back = np.asarray(mesh.vertex_normals, dtype=np.float32)[:, 2] < 0.0
        colors[back] = (colors[back] * 0.35).astype(np.uint8)
    except Exception:  # noqa: BLE001
        pass
    rgba = np.concatenate(
        [colors, np.full((colors.shape[0], 1), 255, dtype=np.uint8)], axis=1,
    )
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=rgba)


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
    # Paint pipeline is optional — a missing `bpy` or a failed texture
    # module does NOT block mesh generation. We serve the untextured
    # shape mesh and log why.
    if Hunyuan3DPaintPipeline is None:
        logger.warning(
            "Hunyuan3D Paint pipeline unavailable — returning untextured "
            "meshes. Attempts:\n  %s", "\n  ".join(paint_errors),
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    # NB: hy3dshape's pipeline's `.to()` is non-standard — it modifies
    # the instance in-place and returns None instead of self. If we
    # chain `.to(device)` we get shape_pipe=None. Keep the assignment
    # separate, and only overwrite shape_pipe if .to() returned a new
    # object (as a normal torch.nn.Module would).
    shape_pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        _HF_REPO, subfolder="hunyuan3d-dit-v2-1",
        torch_dtype=dtype,
    )
    if shape_pipe is None:
        raise RuntimeError("Hunyuan3D shape pipeline: from_pretrained returned None")
    if hasattr(shape_pipe, "to"):
        moved = shape_pipe.to(device)
        if moved is not None:
            shape_pipe = moved

    paint_pipe = None
    if Hunyuan3DPaintPipeline is not None:
        try:
            paint_pipe = Hunyuan3DPaintPipeline.from_pretrained(
                _HF_REPO, subfolder="hunyuan3d-paintpbr-v2-1",
            )
            if paint_pipe is not None and hasattr(paint_pipe, "to"):
                moved = paint_pipe.to(device)
                if moved is not None:
                    paint_pipe = moved
        except Exception as exc:  # noqa: BLE001
            logger.warning("paint pipeline weights load failed (%s); "
                           "untextured meshes only", exc)
            paint_pipe = None

    logger.info("hunyuan3d loaded on %s (%s); shape_pipe=%s paint_pipe=%s",
                device, dtype, type(shape_pipe).__name__,
                "enabled" if paint_pipe else "disabled")
    return _Hunyuan3DHandle(shape_pipe, paint_pipe)
