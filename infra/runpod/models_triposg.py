"""TripoSG 1.5B loader for the RunPod mesh-gen server.

Reference: VAST-AI-Research/TripoSG on HF (MIT, Jan 2026). Rectified-flow
image-to-3D that runs well on a single A100.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

logger = logging.getLogger("vid2sim.pod.triposg")

_HF_REPO = "VAST-AI/TripoSG"


class _TripoSGHandle:
    def __init__(self, pipe):
        self.pipe = pipe

    def generate(self, rgb_bytes: bytes, mask_bytes: bytes) -> bytes:
        from PIL import Image

        rgb = Image.open(io.BytesIO(rgb_bytes)).convert("RGB")
        mask = Image.open(io.BytesIO(mask_bytes)).convert("L")
        out = self.pipe(
            image=rgb, mask=mask,
            num_inference_steps=50,
            guidance_scale=7.0,
        )
        # The pipeline returns either a trimesh or (vertices, faces).
        if hasattr(out, "export"):
            mesh = out
        else:
            import trimesh
            vertices, faces = out[0], out[1]
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
        buf = io.BytesIO()
        mesh.export(buf, file_type="glb")
        return buf.getvalue()


def load(weights_dir: Path) -> _TripoSGHandle:
    import torch

    weights_dir = Path(weights_dir)
    cache = weights_dir / "triposg-1.5b"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(weights_dir / "hf"))

    # TripoSG ships either as a `diffusers`-style pipeline or a custom
    # inference class. Try the official wrapper first; fall back to
    # hand-rolled pipeline.
    try:
        from triposg.pipelines import TripoSGPipeline  # type: ignore
    except ImportError:  # pragma: no cover
        from triposg.pipeline import TripoSGPipeline  # type: ignore

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    pipe = TripoSGPipeline.from_pretrained(
        _HF_REPO, cache_dir=str(cache), torch_dtype=dtype,
    ).to(device)
    logger.info("triposg pipeline loaded on %s (%s)", device, dtype)
    return _TripoSGHandle(pipe)
