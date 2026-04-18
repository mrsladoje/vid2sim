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

    # TripoSG's own scripts use:
    #   from triposg.pipelines.pipeline_triposg import TripoSGPipeline
    #   pipe = TripoSGPipeline.from_pretrained(weights_dir).to(device, dtype)
    # `.to()` takes two positional args (device, dtype) — different from
    # the normal torch.nn.Module contract.
    errors: list[str] = []
    TripoSGPipeline = None
    for mod_path in (
        "triposg.pipelines.pipeline_triposg",
        "triposg.pipelines",
        "triposg.pipeline",
        "triposg",
        "triposg.inference",
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

    # TripoSGPipeline.from_pretrained takes a weights directory, not a
    # HF repo ID by default. Resolve via snapshot_download so we get a
    # concrete local path under our persistent cache.
    from huggingface_hub import snapshot_download

    weights_path = snapshot_download(repo_id=_HF_REPO, cache_dir=str(cache))
    logger.info("triposg weights at %s", weights_path)

    pipe = TripoSGPipeline.from_pretrained(weights_path)
    if pipe is None:
        raise RuntimeError("TripoSGPipeline.from_pretrained returned None")
    if hasattr(pipe, "to"):
        # TripoSG uses a two-arg .to(device, dtype) — non-standard.
        # Be defensive about the return value.
        moved = pipe.to(device, dtype)
        if moved is not None:
            pipe = moved

    logger.info("triposg pipeline loaded on %s (%s); type=%s",
                device, dtype, type(pipe).__name__)
    return _TripoSGHandle(pipe)
