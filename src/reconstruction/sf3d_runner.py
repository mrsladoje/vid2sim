"""SF3D local MPS last-resort mesh generator (ADR-009 §fallback order).

On M3 Max this wraps the Stable Fast 3D model and runs one pass on MPS.
The heavy import is deferred so tests and CI can exercise the fallback
interface without Torch / MPS available — callers pass `model_fn=` to
inject their own generator for tests.

Runtime behaviour in the hackathon:
- If Torch / SF3D weights are present, the first call pays a one-time
  model-load tax (~20-40 s on M3 Max), then ~25-40 s/object thereafter.
- If weights are absent, we fall through to `_stub_glb` so the pipeline
  never blocks Person 3.
"""

from __future__ import annotations

import logging
import os
import struct
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

ModelFn = Callable[[bytes, bytes], bytes]


class SF3DRunner:
    """Implements the `LocalFallback` protocol from runpod_client."""

    def __init__(
        self,
        model_fn: Optional[ModelFn] = None,
        weights_dir: Path | None = None,
    ) -> None:
        self._model_fn = model_fn
        self._weights_dir = weights_dir or Path(
            os.environ.get("SF3D_WEIGHTS", str(Path.home() / ".cache/sf3d"))
        )

    def generate_mesh(self, rgb_jpeg: bytes, mask_png: bytes) -> bytes:
        fn = self._model_fn or _lazy_mps_model(self._weights_dir)
        if fn is None:
            logger.warning(
                "SF3D weights not available at %s — returning stub mesh",
                self._weights_dir,
            )
            return _stub_glb()
        return fn(rgb_jpeg, mask_png)


def _stub_glb() -> bytes:
    return b"glTF" + struct.pack("<II", 2, 12)


def _lazy_mps_model(weights_dir: Path) -> Optional[ModelFn]:
    """On M3 Max, returns a callable that runs SF3D on MPS; None if deps
    or weights are missing. We never import torch at module top level so
    the CI Linux image doesn't need torch installed.
    """
    if not weights_dir.exists():
        return None
    try:
        import torch  # noqa: F401
    except ImportError:
        return None

    try:
        # The `sf3d` package is the Stability AI reference
        # implementation. Import lazily; failure is fine — we fall back.
        from sf3d.system import SF3D  # type: ignore
    except ImportError:
        return None

    # Build the model once and close over it.
    model = SF3D.from_pretrained(str(weights_dir))

    def _run(rgb_jpeg: bytes, mask_png: bytes) -> bytes:
        from io import BytesIO

        from PIL import Image

        rgb = Image.open(BytesIO(rgb_jpeg)).convert("RGB")
        mask = Image.open(BytesIO(mask_png)).convert("L")
        mesh = model.run_image(rgb, mask=mask)  # type: ignore[attr-defined]
        buf = BytesIO()
        mesh.export(buf, file_type="glb")
        return buf.getvalue()

    return _run
