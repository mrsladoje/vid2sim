"""RunPod client tests.

All tests use httpx MockTransport so no network I/O happens.
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from reconstruction.runpod_client import (
    RunPodClient,
    RunPodConfig,
)


def _config(**over) -> RunPodConfig:
    defaults = dict(
        endpoint="https://test.invalid",
        request_timeout_s=1.0,
        connect_timeout_s=1.0,
        retries_per_call=1,
        primary_model="hunyuan3d",
        failure_threshold=2,
        recovery_probe_s=5.0,
    )
    defaults.update(over)
    return RunPodConfig(**defaults)


class _RecordingFallback:
    def __init__(self, payload: bytes = b"SF3D_GLB") -> None:
        self.payload = payload
        self.calls: int = 0

    def generate_mesh(self, rgb_jpeg: bytes, mask_png: bytes) -> bytes:
        self.calls += 1
        return self.payload


def _mock_transport_success(glb: bytes = b"glTF_ok"):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/mesh"
        assert request.method == "POST"
        assert b"model" in request.content
        return httpx.Response(
            200, content=glb,
            headers={
                "Content-Type": "model/gltf-binary",
                "X-Vid2Sim-PodId": "a100-test",
            },
        )
    return httpx.MockTransport(handler)


def _mock_transport_fail(status: int = 503):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="bad")
    return httpx.MockTransport(handler)


def _mock_transport_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)
    return httpx.MockTransport(handler)


def test_successful_call_returns_runpod_provenance() -> None:
    with RunPodClient(_config(), transport=_mock_transport_success(b"REAL_GLB")) as c:
        out = c.generate_mesh(b"jpg", b"png")
    assert out.glb_bytes == b"REAL_GLB"
    assert out.mesh_origin == "hunyuan3d_2.1"
    assert out.mesh_origin_detail == "runpod:hunyuan3d_2.1"
    assert out.ran_on == "runpod"
    assert out.pod_id == "a100-test"
    assert out.attempts == 1


def test_model_triposg_gets_triposg_provenance() -> None:
    with RunPodClient(_config(), transport=_mock_transport_success()) as c:
        out = c.generate_mesh(b"jpg", b"png", model="triposg")
    assert out.mesh_origin == "triposg_1.5b"
    assert out.mesh_origin_detail == "runpod:triposg_1.5b"


def test_retry_then_fallback_goes_to_sf3d() -> None:
    fallback = _RecordingFallback(b"SF3D_BYTES")
    with RunPodClient(
        _config(retries_per_call=2),
        transport=_mock_transport_fail(),
        local_fallback=fallback,
    ) as c:
        out = c.generate_mesh(b"jpg", b"png")
    assert out.glb_bytes == b"SF3D_BYTES"
    assert out.mesh_origin == "sf3d"
    assert out.mesh_origin_detail == "local:sf3d"
    assert out.ran_on == "local"
    assert fallback.calls == 1
    # pod returned errors so SF3D fired
    assert out.error and "503" in out.error


def test_circuit_breaker_opens_after_threshold_then_skips_pod() -> None:
    fallback = _RecordingFallback()
    transport = _mock_transport_fail()
    clock = {"t": 0.0}

    def now_fn() -> float:
        clock["t"] += 0.01
        return clock["t"]

    with RunPodClient(
        _config(failure_threshold=2, retries_per_call=0, recovery_probe_s=100.0),
        transport=transport,
        local_fallback=fallback,
        now_fn=now_fn,
    ) as c:
        c.generate_mesh(b"1", b"1")  # fail 1
        c.generate_mesh(b"2", b"2")  # fail 2 → breaker opens
        # Subsequent calls should skip the pod entirely.
        out = c.generate_mesh(b"3", b"3")
        out2 = c.generate_mesh(b"4", b"4")
    # Fallback called at least 4x (2 pod fails + 2 breaker-open routes)
    assert fallback.calls >= 4
    assert out.mesh_origin == "sf3d"
    assert out2.mesh_origin == "sf3d"


def test_circuit_breaker_reopens_pod_after_recovery_window() -> None:
    """After recovery_probe_s passes, we probe the pod again."""
    success_after_n = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        success_after_n["count"] += 1
        if success_after_n["count"] <= 2:
            return httpx.Response(503, text="cold")
        return httpx.Response(200, content=b"warm", headers={"X-Vid2Sim-PodId": "p"})

    transport = httpx.MockTransport(handler)
    fallback = _RecordingFallback()
    # Mutable virtual clock: test advances it explicitly between calls.
    clock = {"t": 0.0}

    def now_fn() -> float:
        return clock["t"]

    with RunPodClient(
        _config(failure_threshold=2, retries_per_call=0, recovery_probe_s=5.0),
        transport=transport,
        local_fallback=fallback,
        now_fn=now_fn,
    ) as c:
        clock["t"] = 0.0
        out1 = c.generate_mesh(b"a", b"a")  # fail 1, no breaker yet
        clock["t"] = 0.1
        out2 = c.generate_mesh(b"b", b"b")  # fail 2, breaker opens
        clock["t"] = 100.0  # past recovery window
        out3 = c.generate_mesh(b"c", b"c")  # probes pod, succeeds
    assert out1.ran_on == "local"
    assert out2.ran_on == "local"
    assert out3.ran_on == "runpod"
    assert out3.glb_bytes == b"warm"


def test_connect_error_counts_as_failure_and_falls_back() -> None:
    fallback = _RecordingFallback(b"lf")
    with RunPodClient(
        _config(retries_per_call=1),
        transport=_mock_transport_raise(),
        local_fallback=fallback,
    ) as c:
        out = c.generate_mesh(b"x", b"y")
    assert out.glb_bytes == b"lf"
    assert fallback.calls == 1


def test_stub_emitted_when_both_paths_fail() -> None:
    class _FailingFallback:
        def generate_mesh(self, rgb, mask):
            raise RuntimeError("mps oom")

    with RunPodClient(
        _config(retries_per_call=0),
        transport=_mock_transport_fail(),
        local_fallback=_FailingFallback(),
    ) as c:
        out = c.generate_mesh(b"x", b"y")
    assert out.mesh_origin_detail == "stub"
    assert out.mesh_origin == "identity"
    assert out.ran_on == "stub"
    assert out.glb_bytes.startswith(b"glTF")


def test_config_from_yaml(tmp_path) -> None:
    p = tmp_path / "runpod.yaml"
    p.write_text(
        "endpoint:\n"
        "  url: https://example\n"
        "client:\n"
        "  request_timeout_s: 2.0\n"
        "  primary_model: triposg\n"
        "watchdog:\n"
        "  failure_threshold: 3\n"
        "fallback:\n"
        "  local_sf3d_enabled: false\n"
    )
    cfg = RunPodConfig.from_yaml(p)
    assert cfg.endpoint == "https://example"
    assert cfg.primary_model == "triposg"
    assert cfg.failure_threshold == 3
    assert cfg.local_sf3d_enabled is False


def test_healthz_returns_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/healthz"
        return httpx.Response(200, json={"status": "ok"})

    with RunPodClient(_config(), transport=httpx.MockTransport(handler)) as c:
        assert c.healthz()["status"] == "ok"


def test_successful_call_resets_breaker() -> None:
    # First fails, breaker half-primed; second succeeds, breaker clears.
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, content=b"x", headers={"X-Vid2Sim-PodId": "p"})

    fallback = _RecordingFallback()
    with RunPodClient(
        _config(failure_threshold=2, retries_per_call=0),
        transport=httpx.MockTransport(handler),
        local_fallback=fallback,
    ) as c:
        c.generate_mesh(b"a", b"a")
        out = c.generate_mesh(b"b", b"b")
    assert out.ran_on == "runpod"
    assert out.pod_id == "p"
