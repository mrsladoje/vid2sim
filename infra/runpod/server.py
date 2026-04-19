"""FastAPI mesh-generation server for the RunPod pod (ADR-009).

Exactly one POST endpoint:

    POST /mesh
        form-data:
            rgb_crop: JPEG bytes
            mask:     PNG bytes
            model:    "hunyuan3d" | "triposg"
        response:
            200 application/octet-stream  → glb bytes
            503 on model load / inference failure

Plus a GET /healthz that reports which models are loaded. The laptop-side
client in `src/reconstruction/runpod_client.py` is the only consumer.

This file is intentionally thin: weight loading and actual inference are
gated behind an environment flag so the image can boot and respond to
/healthz within seconds; the heavy model graphs load lazily on first
/mesh call (or eagerly via `prewarm.py` during the T-60 ritual).
"""

from __future__ import annotations

import io
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

logger = logging.getLogger("vid2sim.pod")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

WEIGHTS_DIR = Path(os.environ.get("WEIGHTS_DIR", "/workspace/weights"))
ENABLE_INFERENCE = os.environ.get("VID2SIM_POD_INFERENCE", "1") == "1"
ALLOWED_MODELS = {"hunyuan3d", "triposg", "sf3d"}
_da3_handle: object | None = None  # populated lazily on first /depth call

app = FastAPI(title="VID2SIM mesh-gen", version="1.0")

# Model handles are populated lazily. In production, `prewarm.py` pokes
# both endpoints once with a cached crop so the first real request is
# warm.
_model_handles: dict[str, object] = {}


def _load_model(model: str) -> object:
    if model in _model_handles:
        return _model_handles[model]
    if not ENABLE_INFERENCE:
        raise HTTPException(
            status_code=503,
            detail="inference disabled via VID2SIM_POD_INFERENCE=0",
        )
    logger.info("loading model %s from %s ...", model, WEIGHTS_DIR)
    # The actual model loads live in a separate module so the image can
    # boot without CUDA (for CI). Import is lazy to keep /healthz cheap.
    if model == "hunyuan3d":
        from models_hunyuan3d import load as _load  # type: ignore
    elif model == "triposg":
        from models_triposg import load as _load  # type: ignore
    elif model == "sf3d":
        from models_sf3d import load as _load  # type: ignore
    else:  # pragma: no cover - validated upstream
        raise HTTPException(status_code=400, detail=f"unknown model: {model}")
    handle = _load(WEIGHTS_DIR)
    _model_handles[model] = handle
    logger.info("loaded %s", model)
    return handle


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "inference_enabled": ENABLE_INFERENCE,
        "weights_dir": str(WEIGHTS_DIR),
        "weights_mounted": WEIGHTS_DIR.exists(),
        "loaded_models": sorted(_model_handles.keys()),
        "allowed_models": sorted(ALLOWED_MODELS),
        "uptime_s": time.monotonic(),
    }


@app.post("/mesh")
async def mesh(
    rgb_crop: UploadFile = File(...),
    mask: UploadFile = File(...),
    model: str = Form(...),
) -> Response:
    if model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"unknown model: {model}")
    rgb_bytes = await rgb_crop.read()
    mask_bytes = await mask.read()
    if not rgb_bytes or not mask_bytes:
        raise HTTPException(status_code=400, detail="empty rgb_crop or mask")

    handle = _load_model(model)
    t0 = time.monotonic()
    try:
        glb_bytes: bytes = handle.generate(rgb_bytes, mask_bytes)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        logger.exception("inference failed for %s", model)
        raise HTTPException(status_code=503, detail=f"inference failed: {exc}") from exc
    dt = time.monotonic() - t0
    logger.info("served %s mesh in %.2fs (%d bytes)", model, dt, len(glb_bytes))
    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={
            "X-Vid2Sim-Model": model,
            "X-Vid2Sim-GenSeconds": f"{dt:.3f}",
            "X-Vid2Sim-PodId": os.environ.get("RUNPOD_POD_ID", "unknown"),
        },
    )


@app.post("/depth")
async def depth(rgb: UploadFile = File(...)) -> Response:
    """Return DA3 metric depth as numpy .npy bytes.

    Body: multipart/form-data with `rgb` (jpeg bytes).
    Response: application/octet-stream — numpy float32 array, HxW, metres.
    Headers: X-Vid2Sim-DepthShape, X-Vid2Sim-DepthMin, X-Vid2Sim-DepthMax.
    """
    global _da3_handle

    if not ENABLE_INFERENCE:
        raise HTTPException(status_code=503,
                            detail="inference disabled via VID2SIM_POD_INFERENCE=0")

    rgb_bytes = await rgb.read()
    if not rgb_bytes:
        raise HTTPException(status_code=400, detail="empty rgb")

    if _da3_handle is None:
        logger.info("loading DA3 model from %s ...", WEIGHTS_DIR)
        try:
            from models_da3 import load as _da3_load  # type: ignore
            _da3_handle = _da3_load(WEIGHTS_DIR)
        except Exception as exc:  # noqa: BLE001
            logger.exception("DA3 load failed")
            raise HTTPException(status_code=503,
                                detail=f"DA3 load failed: {exc}") from exc

    t0 = time.monotonic()
    try:
        import numpy as np  # noqa: F401
        depth_arr = _da3_handle.predict(rgb_bytes)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        logger.exception("DA3 inference failed")
        raise HTTPException(status_code=503,
                            detail=f"DA3 inference failed: {exc}") from exc
    dt = time.monotonic() - t0

    import numpy as np
    buf = io.BytesIO()
    np.save(buf, depth_arr, allow_pickle=False)
    body = buf.getvalue()
    logger.info("served depth in %.2fs (%d bytes, shape=%s)",
                dt, len(body), depth_arr.shape)
    return Response(
        content=body,
        media_type="application/octet-stream",
        headers={
            "X-Vid2Sim-DepthShape": f"{depth_arr.shape[0]},{depth_arr.shape[1]}",
            "X-Vid2Sim-DepthMin": f"{float(depth_arr.min()):.3f}",
            "X-Vid2Sim-DepthMax": f"{float(depth_arr.max()):.3f}",
            "X-Vid2Sim-DepthSeconds": f"{dt:.3f}",
        },
    )


@app.post("/_selftest")
def selftest() -> dict:
    """Local-only: returns a synthetic cube glb so we can test the HTTP
    path end-to-end without CUDA. Guarded by an env flag; refuses when
    inference is enabled (i.e. on a real production pod)."""
    if ENABLE_INFERENCE:
        raise HTTPException(status_code=403, detail="selftest disabled on production pods")
    import struct

    # 12-byte GLB stub header so clients see a "well-formed-looking" glb
    header = b"glTF" + struct.pack("<II", 2, 12)
    return Response(content=header, media_type="model/gltf-binary")  # type: ignore[return-value]
