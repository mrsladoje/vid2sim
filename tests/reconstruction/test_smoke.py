"""G0 smoke: the package imports and advertises its submodules."""

from __future__ import annotations

import reconstruction


def test_package_advertises_modules() -> None:
    for name in (
        "fusion",
        "backproject",
        "stub_emitter",
        "runpod_client",
        "sf3d_runner",
        "icp_align",
        "decimate",
        "vio",
        "pod_watchdog",
    ):
        assert name in reconstruction.__all__
