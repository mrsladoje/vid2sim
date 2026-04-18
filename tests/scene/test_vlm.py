"""VLM wiring + fallback tests.

We do not hit real APIs in CI. We inject a fake client and check:
  - schema-valid responses round-trip to a PhysicsEstimate.
  - schema-invalid responses silently fall back to the lookup table.
  - network errors silently fall back to the lookup table.
  - the visual-prompting helper writes a non-trivial PNG.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from scene import vlm


class _FakeOK:
    def infer(self, class_name, image_bytes):
        return {
            "mass_kg": 4.2,
            "friction": 0.4,
            "restitution": 0.25,
            "material": "wood",
            "is_rigid": True,
            "reasoning": "fake",
        }


class _FakeBad:
    def infer(self, class_name, image_bytes):
        return {"mass_kg": -1.0}  # missing + invalid


class _FakeBoom:
    def infer(self, class_name, image_bytes):
        raise TimeoutError("boom")


def _crop(tmp_path: Path) -> Path:
    p = tmp_path / "crop.png"
    Image.new("RGB", (96, 96), (20, 50, 200)).save(p)
    return p


def test_ok_response(tmp_path):
    est = vlm.estimate_physics("chair", _crop(tmp_path), (0.5, 0.9, 0.5), client=_FakeOK())
    assert est.source == "vlm"
    assert est.mass_kg == 4.2
    assert est.material == "wood"


def test_bad_response_falls_back(tmp_path):
    est = vlm.estimate_physics("chair", _crop(tmp_path), (0.5, 0.9, 0.5), client=_FakeBad())
    assert est.source == "lookup"
    assert est.mass_kg == 5.0  # chair lookup


def test_timeout_falls_back(tmp_path):
    est = vlm.estimate_physics("ball", _crop(tmp_path), (0.24, 0.24, 0.24), client=_FakeBoom())
    assert est.source == "lookup"
    assert est.material == "rubber"


def test_visual_prompt_produces_png(tmp_path):
    out = vlm.prepare_visual_prompt(_crop(tmp_path), (0.5, 0.9, 0.5))
    assert out[:8] == b"\x89PNG\r\n\x1a\n"


def test_coerce_clips_out_of_range():
    est = vlm._coerce(
        {"mass_kg": 1.0, "friction": -3.0, "restitution": 2.0,
         "material": "alien", "is_rigid": True},
        source="vlm",
    )
    assert est.friction == 0.0
    assert est.restitution == 1.0
    assert est.material == "unknown"
