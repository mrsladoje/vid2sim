"""Pod health watchdog (plan §G3).

Polls `GET /healthz` on the RunPod endpoint; after
`failure_threshold` consecutive failures, trips the circuit-breaker
inside a `RunPodClient` so the next mesh call re-routes to SF3D
without a network round-trip.

This keeps pod-observability decoupled from the per-object hot path:
the orchestrator spawns a watchdog (typically as a thread) and reads
`is_healthy()` / `last_status()` for logging.

Designed pure-sync first so tests don't need threading. A convenience
`run_forever()` is provided for production.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .runpod_client import RunPodClient

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    ok: bool
    latency_s: float
    payload: dict = field(default_factory=dict)
    error: Optional[str] = None


class PodWatchdog:
    def __init__(
        self,
        client: RunPodClient,
        failure_threshold: int = 2,
        poll_interval_s: float = 5.0,
    ) -> None:
        self._client = client
        self._threshold = failure_threshold
        self._poll_interval_s = poll_interval_s
        self._consecutive_failures = 0
        self._tripped = False
        self._last: Optional[HealthStatus] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- public sync API -------------------------------------------

    def check_once(self) -> HealthStatus:
        t0 = time.monotonic()
        try:
            payload = self._client.healthz()
            status = HealthStatus(ok=True, latency_s=time.monotonic() - t0,
                                  payload=payload)
        except (httpx.HTTPError, Exception) as exc:  # noqa: BLE001
            status = HealthStatus(
                ok=False, latency_s=time.monotonic() - t0,
                error=str(exc),
            )

        with self._lock:
            self._last = status
            if status.ok:
                if self._consecutive_failures:
                    logger.info("pod healthy again after %d failure(s)",
                                self._consecutive_failures)
                self._consecutive_failures = 0
                self._tripped = False
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self._threshold:
                    if not self._tripped:
                        logger.warning("pod watchdog tripped circuit breaker "
                                       "after %d consecutive failures",
                                       self._consecutive_failures)
                    self._tripped = True
                    # Directly flip the client's internal breaker so the
                    # next generate_mesh() short-circuits to SF3D.
                    self._client._breaker.consecutive_failures = \
                        max(self._client._breaker.consecutive_failures,
                            self._client._cfg.failure_threshold)
                    self._client._breaker.opened_at = time.monotonic()
        return status

    def is_healthy(self) -> bool:
        with self._lock:
            return bool(self._last and self._last.ok and not self._tripped)

    def last_status(self) -> Optional[HealthStatus]:
        with self._lock:
            return self._last

    def has_tripped(self) -> bool:
        with self._lock:
            return self._tripped

    # ---- background thread -----------------------------------------

    def run_forever(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="pod-watchdog"
        )
        self._stop.clear()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("watchdog loop crash: %s", exc)
            self._stop.wait(self._poll_interval_s)
