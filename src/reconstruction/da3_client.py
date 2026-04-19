"""Laptop-side DA3 client. Posts an RGB jpeg to the RunPod pod's
`/depth` endpoint and returns a (H, W) float32 metric-depth array in
metres, alongside provenance.

Usage:
    from reconstruction.da3_client import DA3Client
    client = DA3Client.from_yaml(Path("config/runpod.yaml"))
    depth = client.predict(rgb_jpeg_bytes)
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DA3Config:
    endpoint: str
    depth_path: str = "/depth"
    request_timeout_s: float = 30.0
    connect_timeout_s: float = 5.0

    @classmethod
    def from_yaml(cls, path: Path) -> "DA3Config":
        with path.open() as fh:
            data = yaml.safe_load(fh)
        ep = data["endpoint"]
        cl = data.get("client", {})
        return cls(
            endpoint=ep["url"],
            depth_path=ep.get("depth_path", "/depth"),
            request_timeout_s=float(cl.get("request_timeout_s", 30.0)),
            connect_timeout_s=float(cl.get("connect_timeout_s", 5.0)),
        )


@dataclass
class DepthResult:
    depth: np.ndarray
    wall_time_s: float
    pod_time_s: float
    min_m: float
    max_m: float


class DA3Client:
    def __init__(self, config: DA3Config,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        self._cfg = config
        self._client = httpx.Client(
            base_url=config.endpoint,
            timeout=httpx.Timeout(
                connect=config.connect_timeout_s,
                read=config.request_timeout_s,
                write=config.request_timeout_s,
                pool=config.request_timeout_s,
            ),
            transport=transport,
        )

    @classmethod
    def from_yaml(cls, path: Path, **kw) -> "DA3Client":
        return cls(DA3Config.from_yaml(path), **kw)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "DA3Client":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def predict(self, rgb_jpeg: bytes) -> DepthResult:
        t0 = time.monotonic()
        resp = self._client.post(
            self._cfg.depth_path,
            files={"rgb": ("frame.jpg", rgb_jpeg, "image/jpeg")},
        )
        resp.raise_for_status()
        depth = np.load(io.BytesIO(resp.content), allow_pickle=False)
        return DepthResult(
            depth=depth.astype(np.float32),
            wall_time_s=time.monotonic() - t0,
            pod_time_s=float(resp.headers.get("X-Vid2Sim-DepthSeconds", "0")),
            min_m=float(resp.headers.get("X-Vid2Sim-DepthMin", "0")),
            max_m=float(resp.headers.get("X-Vid2Sim-DepthMax", "0")),
        )

    def predict_path(self, image_path: Path) -> DepthResult:
        return self.predict(Path(image_path).read_bytes())
