"""Exporters for the frozen `scene.json` contract.

Primary : glTF + sidecar physics JSON  (plan §4)
Required: MJCF, MuJoCo `.py`
Stretch : USD
"""

from .gltf import export_gltf
from .mjcf import export_mjcf
from .mujoco_py import export_mujoco_py

__all__ = ["export_gltf", "export_mjcf", "export_mujoco_py"]

try:  # stretch
    from .usd import export_usd  # noqa: F401
    __all__.append("export_usd")
except Exception:  # pragma: no cover - usd-core is optional
    pass
