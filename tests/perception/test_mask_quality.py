"""Mask quality gate from plan §6 G2: IoU(class mask, object bbox) >= 0.6.

On real captures this is the "does YOLOE really line up with the RGB"
check; on the stub bundle it doubles as a regression test that the stub
generator produces non-degenerate masks (catching the 1x1-blob bug).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.perception.bundle import BundleReader


def _iou(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    a = mask_a.astype(bool)
    b = mask_b.astype(bool)
    union = np.logical_or(a, b).sum()
    if union == 0:
        return 1.0 if np.array_equal(a, b) else 0.0
    inter = np.logical_and(a, b).sum()
    return float(inter) / float(union)


def _bbox_mask(shape: tuple[int, int], bbox: tuple[int, int, int, int]) -> np.ndarray:
    h, w = shape
    m = np.zeros((h, w), dtype=bool)
    x1, y1, x2, y2 = bbox
    x1, y1 = max(x1, 0), max(y1, 0)
    x2, y2 = min(x2, w), min(y2, h)
    if x2 > x1 and y2 > y1:
        m[y1:y2, x1:x2] = True
    return m


@pytest.fixture(scope="module")
def sampled_frames(stub_bundle: Path) -> list:
    reader = BundleReader(stub_bundle)
    # Plan asks for 5 sampled frames; bundle in CI has 8 -> evenly spaced sample.
    n = len(reader)
    idxs = np.linspace(0, n - 1, num=min(5, n), dtype=int).tolist()
    return [reader.read(i) for i in idxs]


def test_class_mask_iou_against_bbox(sampled_frames) -> None:
    scores = []
    for rec in sampled_frames:
        if not rec.objects:
            pytest.skip("no objects in bundle; skip IoU check")
        # Take the first object (stub has exactly one).
        obj = rec.objects[0]
        bbox_mask = _bbox_mask(rec.mask_class.shape, obj.bbox2d)
        detected_mask = rec.mask_class > 0
        scores.append(_iou(bbox_mask, detected_mask))
    avg = sum(scores) / len(scores)
    assert avg >= 0.6, f"mask IoU {avg:.3f} below G2 gate of 0.6 (per-frame={scores})"


def test_mask_is_not_a_stub_blob(stub_bundle: Path) -> None:
    reader = BundleReader(stub_bundle)
    rec = reader.read(0)
    assert rec.mask_class.size > 1_000_000, "mask is a 1x1 blob"
    assert (rec.mask_class > 0).sum() > 1_000, "less than 1k foreground pixels — likely broken"
