"""Pod watchdog tests (pure-sync; no threads)."""

from __future__ import annotations

import httpx

from reconstruction.pod_watchdog import PodWatchdog
from reconstruction.runpod_client import RunPodClient, RunPodConfig


def _client(handler) -> RunPodClient:
    return RunPodClient(
        RunPodConfig(endpoint="https://test.invalid", failure_threshold=2,
                     retries_per_call=0),
        transport=httpx.MockTransport(handler),
    )


def test_healthy_pod_stays_healthy() -> None:
    def ok(_req):
        return httpx.Response(200, json={"status": "ok"})

    c = _client(ok)
    wd = PodWatchdog(c, failure_threshold=2)
    for _ in range(3):
        wd.check_once()
    assert wd.is_healthy()
    assert not wd.has_tripped()


def test_two_consecutive_failures_trip_circuit() -> None:
    calls = {"n": 0}

    def flaky(_req):
        calls["n"] += 1
        return httpx.Response(503, text="bad")

    c = _client(flaky)
    wd = PodWatchdog(c, failure_threshold=2)
    wd.check_once()
    assert not wd.has_tripped()  # 1 fail — not yet
    wd.check_once()
    assert wd.has_tripped()  # 2 fails — trip
    assert not wd.is_healthy()


def test_recovery_clears_counter() -> None:
    n = {"count": 0}

    def seq(_req):
        n["count"] += 1
        if n["count"] <= 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"status": "ok"})

    c = _client(seq)
    wd = PodWatchdog(c, failure_threshold=3)
    wd.check_once()  # fail 1
    assert not wd.has_tripped()
    wd.check_once()  # success — resets
    assert wd.is_healthy()
    assert not wd.has_tripped()


def test_last_status_is_populated() -> None:
    def ok(_req):
        return httpx.Response(200, json={"status": "ok", "inference_enabled": True})

    c = _client(ok)
    wd = PodWatchdog(c)
    wd.check_once()
    s = wd.last_status()
    assert s is not None and s.ok
    assert s.payload["inference_enabled"] is True


def test_connect_error_counts_as_failure() -> None:
    def boom(req):
        raise httpx.ConnectError("nope", request=req)

    c = _client(boom)
    wd = PodWatchdog(c, failure_threshold=2)
    wd.check_once()
    wd.check_once()
    assert wd.has_tripped()
    s = wd.last_status()
    assert s is not None and not s.ok and s.error


def test_trip_flips_client_breaker_so_mesh_calls_skip_pod() -> None:
    fail_count = {"n": 0}

    def healthz_fail(_req):
        return httpx.Response(503, text="down")

    c = RunPodClient(
        RunPodConfig(endpoint="https://test.invalid", failure_threshold=3,
                     retries_per_call=0, recovery_probe_s=1000.0),
        transport=httpx.MockTransport(healthz_fail),
    )

    wd = PodWatchdog(c, failure_threshold=2)
    wd.check_once()
    wd.check_once()  # trip

    # Now a mesh call should see the tripped breaker. We don't have a
    # fallback wired, so stub_on_double_failure produces a stub glb.
    out = c.generate_mesh(b"a", b"b")
    assert out.ran_on == "stub"
