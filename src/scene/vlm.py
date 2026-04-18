"""VLM physics-property inference.

Stack (per plan §1):
    primary : Claude Opus 4.7    (claude-opus-4-7)
    backup  : Gemini 3.1 Pro
    cheap   : Qwen3-VL-30B-A3B-Instruct

Wrapped in PhysQuantAgent-style visual prompting: visual markers (bbox,
reference-scale ruler, centroid dot) are rendered onto the crop before the
VLM sees it. The VLM is told to estimate mass / friction / restitution /
material / is_rigid as structured JSON. Schema-validated on return; on
timeout, schema failure, or any API error we silently fall back to the
lookup table (plan §6 G2 fallback: "VLM schema violation: fall back to
lookup; flag coverage gap and continue").
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw

from . import lookup

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-4-7"
DEFAULT_TIMEOUT_S = 20.0

_SYSTEM_PROMPT = (
    "You are a physics-property estimator for a rigid-body simulator. "
    "Given one cropped image of an everyday object with visual markers overlaid "
    "(green bbox, centroid dot, red reference ruler in meters), return ONLY a "
    "JSON object with keys: mass_kg (positive float), friction (0..2), "
    "restitution (0..1), material (one of: wood, metal, plastic, rubber, "
    "glass, ceramic, fabric, paper, stone, unknown), is_rigid (bool), "
    "reasoning (short string). No prose outside the JSON."
)


@dataclass(frozen=True)
class PhysicsEstimate:
    mass_kg: float
    friction: float
    restitution: float
    material: str
    is_rigid: bool
    reasoning: str
    source: str  # "vlm" | "lookup"


class VLMClient(Protocol):
    def infer(self, class_name: str, image_bytes: bytes) -> dict: ...


# ---------- visual prompting ---------------------------------------------------

def prepare_visual_prompt(
    crop_path: Path,
    bbox_size_m: tuple[float, float, float] | None = None,
) -> bytes:
    """Overlay markers on a crop. PhysQuantAgent-style (arXiv 2603.16958).

    Markers: green bounding-rectangle, centroid dot, red reference ruler
    whose length encodes the real-world longest bbox side in meters.
    """
    img = Image.open(crop_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    margin = int(min(w, h) * 0.04)
    draw.rectangle(
        (margin, margin, w - margin, h - margin),
        outline=(0, 255, 0),
        width=max(2, int(min(w, h) * 0.006)),
    )

    cx, cy = w // 2, h // 2
    r = max(3, int(min(w, h) * 0.01))
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 255, 0))

    if bbox_size_m is not None:
        longest = max(bbox_size_m)
        ruler_px = int((w - 2 * margin) * 0.6)
        x0 = margin
        y0 = h - margin - 10
        draw.line((x0, y0, x0 + ruler_px, y0), fill=(255, 0, 0), width=3)
        draw.text((x0, y0 - 16), f"{longest:.2f} m", fill=(255, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------- providers ----------------------------------------------------------

class ClaudeClient:
    """Claude Opus 4.7 vision client. Lazy-imports anthropic."""

    def __init__(self, model: str = CLAUDE_MODEL, timeout_s: float = DEFAULT_TIMEOUT_S):
        self.model = model
        self.timeout_s = timeout_s

    def infer(self, class_name: str, image_bytes: bytes) -> dict:
        from anthropic import Anthropic  # lazy

        client = Anthropic(timeout=self.timeout_s)
        encoded = base64.standard_b64encode(image_bytes).decode()
        resp = client.messages.create(
            model=self.model,
            max_tokens=512,
            system=[{"type": "text", "text": _SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png", "data": encoded}},
                    {"type": "text",
                     "text": f"Object class label: {class_name}. Return JSON only."},
                ],
            }],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return _parse_json(text)


class GeminiClient:
    """Gemini 3.1 Pro backup. Activated via VID2SIM_VLM=gemini."""

    def __init__(self, model: str = "gemini-3.1-pro", timeout_s: float = DEFAULT_TIMEOUT_S):
        self.model = model
        self.timeout_s = timeout_s

    def infer(self, class_name: str, image_bytes: bytes) -> dict:
        from google import genai  # lazy

        client = genai.Client()
        resp = client.models.generate_content(
            model=self.model,
            contents=[
                _SYSTEM_PROMPT,
                {"inline_data": {"mime_type": "image/png", "data": image_bytes}},
                f"Object class label: {class_name}. Return JSON only.",
            ],
        )
        return _parse_json(resp.text)


class QwenClient:
    """Qwen3-VL-30B-A3B-Instruct via an OpenAI-compatible endpoint."""

    def __init__(
        self,
        model: str = "Qwen/Qwen3-VL-30B-A3B-Instruct",
        base_url: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ):
        self.model = model
        self.base_url = base_url or os.environ.get(
            "QWEN_BASE_URL", "http://localhost:8000/v1"
        )
        self.timeout_s = timeout_s

    def infer(self, class_name: str, image_bytes: bytes) -> dict:
        from openai import OpenAI  # lazy

        client = OpenAI(base_url=self.base_url, timeout=self.timeout_s,
                        api_key=os.environ.get("QWEN_API_KEY", "EMPTY"))
        encoded = base64.standard_b64encode(image_bytes).decode()
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                    {"type": "text",
                     "text": f"Object class label: {class_name}. Return JSON only."},
                ]},
            ],
            response_format={"type": "json_object"},
        )
        return _parse_json(resp.choices[0].message.content or "")


# ---------- orchestration ------------------------------------------------------

def default_client() -> VLMClient:
    choice = os.environ.get("VID2SIM_VLM", "claude").lower()
    if choice == "gemini":
        return GeminiClient()
    if choice == "qwen":
        return QwenClient()
    return ClaudeClient()


def estimate_physics(
    class_name: str,
    crop_path: Path,
    bbox_size_m: tuple[float, float, float] | None = None,
    client: VLMClient | None = None,
) -> PhysicsEstimate:
    """Run the VLM; on *any* failure fall back to the lookup table."""
    client = client or default_client()
    try:
        image_bytes = prepare_visual_prompt(crop_path, bbox_size_m)
        raw = client.infer(class_name, image_bytes)
        return _coerce(raw, source="vlm")
    except Exception as exc:  # noqa: BLE001 — by design per plan §6 G2
        logger.warning("VLM inference failed for %s (%s); using lookup", class_name, exc)
        phys = lookup.physics_for(class_name)
        return PhysicsEstimate(
            mass_kg=phys["mass_kg"],
            friction=phys["friction"],
            restitution=phys["restitution"],
            material=lookup.material_for(class_name),
            is_rigid=phys["is_rigid"],
            reasoning="",
            source="lookup",
        )


# ---------- helpers ------------------------------------------------------------

_REQUIRED_KEYS = {"mass_kg", "friction", "restitution", "material", "is_rigid"}
_ALLOWED_MATERIALS = {
    "wood", "metal", "plastic", "rubber", "glass",
    "ceramic", "fabric", "paper", "stone", "unknown",
}


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _coerce(raw: dict, source: str) -> PhysicsEstimate:
    missing = _REQUIRED_KEYS - raw.keys()
    if missing:
        raise ValueError(f"VLM response missing keys: {missing}")
    material = raw["material"]
    if material not in _ALLOWED_MATERIALS:
        material = "unknown"
    mass = float(raw["mass_kg"])
    friction = max(0.0, float(raw["friction"]))
    restitution = min(1.0, max(0.0, float(raw["restitution"])))
    if mass <= 0:
        raise ValueError(f"VLM returned non-positive mass: {mass}")
    return PhysicsEstimate(
        mass_kg=mass,
        friction=friction,
        restitution=restitution,
        material=material,
        is_rigid=bool(raw["is_rigid"]),
        reasoning=str(raw.get("reasoning", "")),
        source=source,
    )
