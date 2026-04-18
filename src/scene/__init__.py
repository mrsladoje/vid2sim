"""VID2SIM Stream 03 — Scene Assembly package.

Owns the frozen `scene.json` contract (ADR-001) and its exporters.
"""

from .assembler import SceneAssembler, AssemblerConfig
from .reconstructed import ReconstructedObject

__all__ = ["SceneAssembler", "AssemblerConfig", "ReconstructedObject"]
__version__ = "1.0.0"
