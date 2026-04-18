"""TripoSG 1.5B loader for the RunPod mesh-gen server.

Reference: VAST-AI/TripoSG (MIT, Jan 2026). Rectified-flow image-to-3D
that runs well on a single A100.

Mirrors `scripts/inference_triposg.py::run_triposg` but skips the BriaRMBG
background-removal model — we already have an object mask from the
upstream perception pipeline, and compositing RGB onto white using the
mask is what `prepare_image` ends up doing anyway. Saves ~1 s per call
plus an extra ~300 MB GPU allocation.

Output gets a fast image-projection vertex-color pass so the glb is not
grey (Paint 2.1 / bpy path is too heavy for the hackathon budget).
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger("vid2sim.pod.triposg")

_HF_REPO = "VAST-AI/TripoSG"


class _TripoSGHandle:
    def __init__(self, pipe, device, dtype):
        self.pipe = pipe
        self.device = device
        self.dtype = dtype

    def generate(self, rgb_bytes: bytes, mask_bytes: bytes) -> bytes:
        import torch
        import trimesh
        from PIL import Image

        # Load inputs
        rgb = Image.open(io.BytesIO(rgb_bytes)).convert("RGB")
        mask = Image.open(io.BytesIO(mask_bytes)).convert("L")
        if mask.size != rgb.size:
            mask = mask.resize(rgb.size, Image.LANCZOS)

        # Prepare_image equivalent: composite object onto white background
        # using the mask (white bg_color per run_triposg default).
        white = Image.new("RGB", rgb.size, (255, 255, 255))
        img = Image.composite(rgb, white, mask)

        # Run the rectified-flow pipeline (matches run_triposg kwargs).
        outputs = self.pipe(
            image=img,
            generator=torch.Generator(device=self.device).manual_seed(42),
            num_inference_steps=50,
            guidance_scale=7.0,
        ).samples[0]
        vertices = outputs[0].astype(np.float32)
        faces = np.ascontiguousarray(outputs[1])
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

        # Fast image-projection vertex coloring (~0.1 s). Gives a
        # coloured glb without needing bpy / Paint 2.1.
        _apply_image_projection_colors(mesh, img)

        buf = io.BytesIO()
        mesh.export(buf, file_type="glb")
        return buf.getvalue()


def _apply_image_projection_colors(mesh, pil_image) -> None:
    """Planar-project the input image onto the mesh's XY and sample
    per-vertex colors. Only front-facing verts (positive Z normal) get
    the sampled colour; back-facing verts get a flat grey.

    Good enough for a single-view capture: what the camera saw is what
    the viewer sees. Runs in numpy — no extra GPU cost.
    """
    import numpy as np
    import trimesh

    img_arr = np.asarray(pil_image.convert("RGB"), dtype=np.uint8)
    h, w = img_arr.shape[:2]

    v = np.asarray(mesh.vertices, dtype=np.float32)
    if v.size == 0:
        return

    # Normalise XY to image UV space. TripoSG output is in a rough
    # unit-cube frame; flipping Y matches image pixel convention.
    x, y = v[:, 0], v[:, 1]
    u_norm = (x - x.min()) / (x.max() - x.min() + 1e-9)
    v_norm = (y - y.min()) / (y.max() - y.min() + 1e-9)
    px = np.clip((u_norm * (w - 1)).astype(np.int32), 0, w - 1)
    py = np.clip(((1.0 - v_norm) * (h - 1)).astype(np.int32), 0, h - 1)

    colors = img_arr[py, px]  # (N, 3)

    # Darken back-facing vertices (normal Z < 0) so the back isn't just
    # repeating the front image.
    try:
        vnorm = np.asarray(mesh.vertex_normals, dtype=np.float32)
        back = vnorm[:, 2] < 0.0
        colors = colors.copy()
        colors[back] = (colors[back] * 0.35).astype(np.uint8)
    except Exception:  # noqa: BLE001
        pass

    rgba = np.concatenate(
        [colors, np.full((colors.shape[0], 1), 255, dtype=np.uint8)],
        axis=1,
    )
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=rgba)


def load(weights_dir: Path) -> _TripoSGHandle:
    import torch

    weights_dir = Path(weights_dir)
    cache = weights_dir / "triposg-1.5b"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(weights_dir / "hf"))

    # Import the real class (mirrors scripts/inference_triposg.py imports)
    errors: list[str] = []
    TripoSGPipeline = None
    for mod_path in (
        "triposg.pipelines.pipeline_triposg",
        "triposg.pipelines",
        "triposg.pipeline",
        "triposg",
    ):
        try:
            mod = __import__(mod_path, fromlist=["TripoSGPipeline"])
            TripoSGPipeline = getattr(mod, "TripoSGPipeline")
            logger.info("triposg pipeline found at %s", mod_path)
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{mod_path}: {type(exc).__name__}: {exc}")
    if TripoSGPipeline is None:
        raise ImportError(
            "could not import TripoSGPipeline; tried:\n  "
            + "\n  ".join(errors)
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    # TripoSGPipeline.from_pretrained takes a weights directory (per
    # scripts/inference_triposg.py line 82-83), not a HF repo ID. Use
    # snapshot_download to get a deterministic local path.
    from huggingface_hub import snapshot_download

    weights_path = snapshot_download(repo_id=_HF_REPO, cache_dir=str(cache))
    logger.info("triposg weights at %s", weights_path)

    pipe = TripoSGPipeline.from_pretrained(weights_path)
    if pipe is None:
        raise RuntimeError("TripoSGPipeline.from_pretrained returned None")
    # Non-standard two-arg .to(device, dtype) per inference_triposg.py:92.
    if hasattr(pipe, "to"):
        moved = pipe.to(device, dtype)
        if moved is not None:
            pipe = moved

    logger.info("triposg loaded on %s (%s); type=%s",
                device, dtype, type(pipe).__name__)
    return _TripoSGHandle(pipe, device=device, dtype=dtype)
