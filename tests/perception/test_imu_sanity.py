"""IMU sanity gate from plan §6 G2: gravity aligned, no dropouts.

We check per-frame IMU density (close to 400 Hz / 15 fps) and that the
accelerometer mean is near the 9.8 m/s^2 gravity magnitude. On real data
this catches a capture that forgot to enable the IMU or ran at the wrong
rate — exactly the 1-sample-per-frame bug the review flagged.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from src.perception.bundle import BundleReader


EXPECTED_IMU_RATE_HZ = 400
FPS = 15
# At 400 Hz / 15 fps we expect ~26 samples; allow [18, 35].
MIN_SAMPLES_PER_FRAME = 18
MAX_SAMPLES_PER_FRAME = 35
GRAVITY = 9.80665


def test_imu_density_close_to_target(stub_bundle: Path) -> None:
    reader = BundleReader(stub_bundle)
    counts = [len(reader.read(i).imu) for i in range(len(reader))]
    assert min(counts) >= MIN_SAMPLES_PER_FRAME, (
        f"IMU dropouts: min samples/frame = {min(counts)} < {MIN_SAMPLES_PER_FRAME} "
        f"(400 Hz / 15 fps should be ~26)"
    )
    assert max(counts) <= MAX_SAMPLES_PER_FRAME, f"suspicious max {max(counts)}"


def test_gravity_is_aligned(stub_bundle: Path) -> None:
    reader = BundleReader(stub_bundle)
    accels: list[tuple[float, float, float]] = []
    for i in range(len(reader)):
        accels.extend(s.accel for s in reader.read(i).imu)
    assert accels, "no IMU samples recorded"
    arr = np.asarray(accels, dtype=float)
    mean_mag = float(np.linalg.norm(arr.mean(axis=0)))
    assert math.isfinite(mean_mag)
    # Accept 8.5..11 m/s^2 — stationary capture, allow sensor bias.
    assert 8.5 <= mean_mag <= 11.0, f"|mean accel| = {mean_mag:.3f} m/s^2, gravity looks wrong"


def test_timestamps_are_monotonic(stub_bundle: Path) -> None:
    reader = BundleReader(stub_bundle)
    ts: list[int] = []
    for i in range(len(reader)):
        ts.extend(s.timestamp_ns for s in reader.read(i).imu)
    assert ts == sorted(ts), "IMU timestamps not monotonic"
    # Spot-check inter-sample spacing is near 1/400 s.
    diffs = np.diff(ts)
    if len(diffs):
        median_dt = float(np.median(diffs))
        assert 1e6 < median_dt < 10e6, f"median IMU dt = {median_dt} ns (expect ~2.5 ms)"
