"""Laptop-side RunPod mesh-generation client (ADR-009).

Usage (production):
    client = RunPodClient.from_yaml(Path("config/runpod.yaml"))
    glb_bytes, prov = client.generate_mesh(rgb_jpeg, mask_png)

Behaviour:
- Posts multipart/form-data to `{endpoint}/mesh` with fields
  `rgb_crop`, `mask`, `model`.
- Retries once on transient errors (per-call, short backoff).
- Circuit-breaker: after N consecutive failures, refuses outgoing calls
  for `recovery_probe_s`; during that window every call flips to the
  local SF3D fallback (if provided).
- Records provenance per call so the caller can stamp the object
  manifest with `mesh_origin_detail`, `ran_on`, `generation_s`.

The class is HTTP-transport-agnostic — tests pass an httpx MockTransport
in so no real network is involved.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import httpx
import yaml

logger = logging.getLogger(__name__)

MeshOriginDetail = str  # "runpod:hunyuan3d_2.1" | "runpod:triposg_1.5b" | "local:sf3d" | "stub"


@dataclass(frozen=True)
class RunPodConfig:
    endpoint: str
    healthz_path: str = "/healthz"
    mesh_path: str = "/mesh"
    request_timeout_s: float = 25.0
    connect_timeout_s: float = 5.0
    retries_per_call: int = 1
    primary_model: str = "hunyuan3d"
    fallback_model: str = "triposg"
    failure_threshold: int = 2
    recovery_probe_s: float = 30.0
    local_sf3d_enabled: bool = True
    stub_on_double_failure: bool = True

    @classmethod
    def from_yaml(cls, path: Path) -> "RunPodConfig":
        with path.open() as fh:
            data = yaml.safe_load(fh)
        ep = data["endpoint"]
        cl = data.get("client", {})
        wd = data.get("watchdog", {})
        fb = data.get("fallback", {})
        return cls(
            endpoint=ep["url"],
            healthz_path=ep.get("healthz_path", "/healthz"),
            mesh_path=ep.get("mesh_path", "/mesh"),
            request_timeout_s=float(cl.get("request_timeout_s", 25.0)),
            connect_timeout_s=float(cl.get("connect_timeout_s", 5.0)),
            retries_per_call=int(cl.get("retries_per_call", 1)),
            primary_model=str(cl.get("primary_model", "hunyuan3d")),
            fallback_model=str(cl.get("fallback_model", "triposg")),
            failure_threshold=int(wd.get("failure_threshold", 2)),
            recovery_probe_s=float(wd.get("recovery_probe_s", 30.0)),
            local_sf3d_enabled=bool(fb.get("local_sf3d_enabled", True)),
            stub_on_double_failure=bool(fb.get("stub_on_double_failure", True)),
        )


class LocalFallback(Protocol):
    """Interface the SF3D runner satisfies."""

    def generate_mesh(self, rgb_jpeg: bytes, mask_png: bytes) -> bytes: ...


@dataclass
class _BreakerState:
    consecutive_failures: int = 0
    opened_at: float | None = None

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self, threshold: int, now: float) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= threshold and self.opened_at is None:
            self.opened_at = now

    def is_open(self, now: float, recovery_s: float) -> bool:
        if self.opened_at is None:
            return False
        if (now - self.opened_at) >= recovery_s:
            # probe window reopened; reset so the next call actually hits
            # the pod and proves it.
            self.consecutive_failures = 0
            self.opened_at = None
            return False
        return True


@dataclass
class MeshCall:
    glb_bytes: bytes
    mesh_origin_detail: MeshOriginDetail
    mesh_origin: str  # scene-schema enum: hunyuan3d_2.1 | triposg_1.5b | sf3d | identity
    ran_on: str      # runpod | local | stub
    generation_s: float
    pod_id: str = ""
    attempts: int = 1
    error: str | None = None


_ORIGIN_ENUM = {
    "hunyuan3d": "hunyuan3d_2.1",
    "triposg": "triposg_1.5b",
    "sf3d": "sf3d",
    "stub": "identity",
}


def _stub_glb() -> bytes:
    """Deterministic tiny stub — only fires on pod+SF3D double failure."""
    import struct
    return b"glTF" + struct.pack("<II", 2, 12)


class RunPodClient:
    def __init__(
        self,
        config: RunPodConfig,
        transport: httpx.BaseTransport | None = None,
        local_fallback: LocalFallback | None = None,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cfg = config
        self._now = now_fn
        self._breaker = _BreakerState()
        self._local_fallback = local_fallback
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

    # ---- public -----------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path, **kwargs) -> "RunPodClient":
        return cls(RunPodConfig.from_yaml(path), **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RunPodClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def healthz(self) -> dict:
        resp = self._client.get(self._cfg.healthz_path)
        resp.raise_for_status()
        return resp.json()

    def generate_mesh(
        self,
        rgb_jpeg: bytes,
        mask_png: bytes,
        *,
        model: str | None = None,
    ) -> MeshCall:
        """Generate a mesh for one object.

        Honours the circuit-breaker: if the breaker is open we go
        straight to SF3D (then to stub) without touching the network.
        """
        chosen = model or self._cfg.primary_model
        if self._breaker.is_open(self._now(), self._cfg.recovery_probe_s):
            logger.warning("runpod circuit-breaker open; going to SF3D")
            return self._fallback(rgb_jpeg, mask_png, reason="breaker_open")

        try:
            return self._call_pod(rgb_jpeg, mask_png, model=chosen)
        except _PodError as exc:
            logger.warning("runpod call failed: %s", exc)
            self._breaker.record_failure(
                self._cfg.failure_threshold, self._now()
            )
            return self._fallback(rgb_jpeg, mask_png, reason=str(exc))

    # ---- internal ---------------------------------------------------

    def _call_pod(self, rgb_jpeg: bytes, mask_png: bytes, *, model: str) -> MeshCall:
        last_error: Exception | None = None
        attempts = 0
        t0 = self._now()
        for attempt in range(self._cfg.retries_per_call + 1):
            attempts = attempt + 1
            try:
                resp = self._client.post(
                    self._cfg.mesh_path,
                    files={
                        "rgb_crop": ("crop.jpg", rgb_jpeg, "image/jpeg"),
                        "mask": ("mask.png", mask_png, "image/png"),
                    },
                    data={"model": model},
                )
            except httpx.HTTPError as exc:
                last_error = exc
                continue

            if resp.status_code == 200:
                dt = self._now() - t0
                self._breaker.record_success()
                return MeshCall(
                    glb_bytes=resp.content,
                    mesh_origin_detail=f"runpod:{_ORIGIN_ENUM[model]}",
                    mesh_origin=_ORIGIN_ENUM[model],
                    ran_on="runpod",
                    generation_s=dt,
                    pod_id=resp.headers.get("X-Vid2Sim-PodId", ""),
                    attempts=attempts,
                )
            last_error = _PodError(f"http {resp.status_code}: {resp.text[:120]}")

        raise _PodError(str(last_error) if last_error else "unknown pod failure")

    def _fallback(self, rgb_jpeg: bytes, mask_png: bytes, *, reason: str) -> MeshCall:
        if self._local_fallback is not None and self._cfg.local_sf3d_enabled:
            t0 = self._now()
            try:
                glb = self._local_fallback.generate_mesh(rgb_jpeg, mask_png)
                return MeshCall(
                    glb_bytes=glb,
                    mesh_origin_detail="local:sf3d",
                    mesh_origin="sf3d",
                    ran_on="local",
                    generation_s=self._now() - t0,
                    attempts=1,
                    error=reason,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("SF3D fallback also failed: %s", exc)
                reason = f"pod_err={reason}; sf3d_err={exc}"

        if self._cfg.stub_on_double_failure:
            return MeshCall(
                glb_bytes=_stub_glb(),
                mesh_origin_detail="stub",
                mesh_origin="identity",
                ran_on="stub",
                generation_s=0.0,
                attempts=0,
                error=reason,
            )
        raise RuntimeError(f"mesh generation failed with no fallback: {reason}")


class _PodError(RuntimeError):
    pass
