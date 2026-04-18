"""Stable Fast 3D loader for the RunPod mesh-gen server.

Reference: stabilityai/stable-fast-3d (HF). Designed for fast,
single-image → UV-mapped, PBR-textured glb in ~3-5 s on A100. Unlike
Hunyuan3D Paint / TripoSG, SF3D ships an end-to-end texturing path
that does NOT require bpy/Blender — its texture head bakes directly
into a UV atlas it generates internally.

Repo: github.com/Stability-AI/stable-fast-3d
HF:   huggingface.co/stabilityai/stable-fast-3d

The pod-side install is a `pip install -e` on the cloned repo + one
HF snapshot download.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

logger = logging.getLogger("vid2sim.pod.sf3d")

_HF_REPO = "stabilityai/stable-fast-3d"


class _SF3DHandle:
    def __init__(self, model, device, dtype):
        self.model = model
        self.device = device
        self.dtype = dtype

    def generate(self, rgb_bytes: bytes, mask_bytes: bytes) -> bytes:
        from PIL import Image

        rgb = Image.open(io.BytesIO(rgb_bytes)).convert("RGB")
        mask = Image.open(io.BytesIO(mask_bytes)).convert("L")
        if mask.size != rgb.size:
            mask = mask.resize(rgb.size, Image.LANCZOS)

        # SF3D wants RGBA where alpha is the object mask. If the source
        # image already had alpha, prefer it; else use the mask we got.
        rgba = rgb.convert("RGBA")
        rgba.putalpha(mask)

        # Run the SF3D pipeline. Reference invocation (from sf3d/demo.py):
        #   trimesh_mesh, glob_dict = model.run_image(rgba, bake_resolution=1024)
        try:
            mesh, _glob = self.model.run_image(
                rgba, bake_resolution=1024, remesh="none",
            )
        except TypeError:
            # Older SF3D signature: run_image(image) only
            mesh, _glob = self.model.run_image(rgba)

        buf = io.BytesIO()
        mesh.export(buf, file_type="glb")
        return buf.getvalue()


def load(weights_dir: Path) -> _SF3DHandle:
    import torch

    weights_dir = Path(weights_dir)
    cache = weights_dir / "sf3d"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(weights_dir / "hf"))

    # The SF3D code lives in the cloned repo at $WEIGHTS_DIR/src/stable-fast-3d
    # and is added to PYTHONPATH by pod_bootstrap.sh. Class name and
    # entry point per their README:
    #   from sf3d.system import SF3D
    #   model = SF3D.from_pretrained('stabilityai/stable-fast-3d')
    errors: list[str] = []
    SF3D = None
    for mod_path, cls in (
        ("sf3d.system", "SF3D"),
        ("stable_fast_3d.system", "SF3D"),
        ("sf3d", "SF3D"),
    ):
        try:
            mod = __import__(mod_path, fromlist=[cls])
            SF3D = getattr(mod, cls)
            logger.info("sf3d found at %s.%s", mod_path, cls)
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{mod_path}: {type(exc).__name__}: {exc}")
    if SF3D is None:
        raise ImportError(
            "could not import SF3D; tried:\n  " + "\n  ".join(errors)
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    model = SF3D.from_pretrained(_HF_REPO)
    if model is None:
        raise RuntimeError("SF3D.from_pretrained returned None")
    if hasattr(model, "to"):
        moved = model.to(device)
        if moved is not None:
            model = moved
    if hasattr(model, "eval"):
        model.eval()

    logger.info("sf3d loaded on %s (%s); type=%s", device, dtype, type(model).__name__)
    return _SF3DHandle(model, device=device, dtype=dtype)
