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

# Lazy-initialised rembg session — loaded once per worker so we don't pay
# the ONNX startup cost on every mesh request.
_REMBG_SESSION = None
_REMBG_TRIED = False


def _refine_alpha_with_rembg(rgba):
    """Run the incoming RGBA through rembg to tighten the alpha channel
    while leaving the RGB channels untouched.

    The upstream client supplies a coarse mask from YOLOv8-Seg that can
    be loose (soft edges, shadows) or — in the current pipeline —
    collapse to a bbox-shaped blob. rembg's u2net model is trained on
    object-on-background photos and cleans that up robustly. We call it
    with `only_mask=True` so it returns a single-channel "L" mask
    instead of re-compositing the image: if we let rembg composite, its
    default behaviour premultiplies RGB by alpha, which zeroes the
    foreground outside the silhouette and forces SF3D's texture head to
    fall back to solid vertex colours (confirmed regression during
    rec_01_sf3d debugging on 2026-04-19 — shape was correct but meshes
    came back as uniform 102,102,102 grey).

    If rembg isn't installed or errors, we return the input unchanged
    so the pod keeps serving requests.
    """
    global _REMBG_SESSION, _REMBG_TRIED
    try:
        if _REMBG_SESSION is None:
            if _REMBG_TRIED:
                return rgba
            _REMBG_TRIED = True
            import rembg  # type: ignore
            _REMBG_SESSION = rembg.new_session("u2net")
            logger.info("rembg session ready (u2net) for alpha refinement (only_mask=True)")
        import rembg  # type: ignore
        from PIL import Image

        refined_mask = rembg.remove(
            rgba, session=_REMBG_SESSION,
            only_mask=True, post_process_mask=True,
        )
        if refined_mask.mode != "L":
            refined_mask = refined_mask.convert("L")
        # Keep the caller's RGB, only swap in the refined alpha.
        out = rgba.copy()
        out.putalpha(refined_mask)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("rembg refinement skipped: %s: %s", type(exc).__name__, exc)
        return rgba


def _resize_foreground_square(image, foreground_ratio: float = 0.85):
    """Crop to the alpha bbox, then center-pad onto a transparent square
    canvas so the foreground occupies `foreground_ratio` of the frame.

    Mirrors the preprocessing SF3D's reference demo does via
    `sf3d.utils.resize_foreground`. We try that utility first — if the
    installed SF3D version exposes it under any of the known module
    paths — and fall back to a pure-PIL/numpy implementation that
    matches its behaviour, so the pod keeps working across SF3D builds.
    """
    # 1) Try the upstream utility so we stay byte-identical to the
    #    reference pipeline where possible.
    for mod_path in ("sf3d.utils", "stable_fast_3d.utils", "sf3d.models.utils"):
        try:
            mod = __import__(mod_path, fromlist=["resize_foreground"])
            fn = getattr(mod, "resize_foreground", None)
            if fn is not None:
                return fn(image, foreground_ratio)
        except Exception:  # noqa: BLE001
            continue

    # 2) Portable fallback — equivalent semantics.
    import numpy as np
    from PIL import Image

    if image.mode != "RGBA":
        image = image.convert("RGBA")
    arr = np.array(image)
    alpha = arr[..., 3]
    if not alpha.any():
        return image  # nothing to centre on; hand back as-is

    ys, xs = np.where(alpha > 0)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    cropped = arr[y0:y1, x0:x1]
    h, w = cropped.shape[:2]

    # Resize the content so its longer side fills `foreground_ratio` of
    # the square canvas, then paste it into the centre of that canvas.
    side = max(h, w)
    canvas_side = int(round(side / foreground_ratio))
    scale = (canvas_side * foreground_ratio) / side
    new_h = max(1, int(round(h * scale)))
    new_w = max(1, int(round(w * scale)))
    resized = Image.fromarray(cropped, mode="RGBA").resize(
        (new_w, new_h), Image.LANCZOS,
    )
    canvas = Image.new("RGBA", (canvas_side, canvas_side), (0, 0, 0, 0))
    off_x = (canvas_side - new_w) // 2
    off_y = (canvas_side - new_h) // 2
    canvas.paste(resized, (off_x, off_y), resized)
    return canvas


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

        # Refine the alpha with rembg so background that leaked through
        # the upstream coarse mask (bbox fallback, shadows, reflections)
        # gets removed before SF3D sees it. Fails closed if rembg isn't
        # installed.
        rgba = _refine_alpha_with_rembg(rgba)

        # Canonicalise the crop exactly like SF3D's reference demo does —
        # crop to the alpha bbox and re-pad onto a square transparent
        # canvas where the foreground fills `foreground_ratio` of the
        # frame. Without this step SF3D receives off-distribution input
        # (non-square, foreground touching the edges, lots of background)
        # and hallucinates rock-like blobs instead of the actual object.
        # See stable-fast-3d/sf3d/demo.py for the upstream invocation.
        rgba = _resize_foreground_square(rgba, foreground_ratio=0.85)

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

    # SF3D's from_pretrained requires explicit config + weight names.
    # Standard names per stabilityai/stable-fast-3d HF repo.
    model = SF3D.from_pretrained(
        _HF_REPO,
        config_name="config.yaml",
        weight_name="model.safetensors",
    )
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
