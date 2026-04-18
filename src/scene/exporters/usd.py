"""USD exporter (stretch).

`usd-core` + `UsdPhysics` schema. Cut at G3 if not clean in 30 minutes
(plan §7 risk row). Optional install: `pip install vid2sim-scene[usd]`.
"""

from __future__ import annotations

from pathlib import Path


def export_usd(scene: dict, session_dir: Path, out_dir: Path) -> Path:
    try:
        from pxr import Usd, UsdGeom, UsdPhysics, Gf  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "usd-core is not installed. Install with `pip install vid2sim-scene[usd]`."
        ) from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "scene.usd"
    stage = Usd.Stage.CreateNew(str(out))
    root = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(root.GetPrim())

    up = scene["world"]["up_axis"].upper()
    UsdGeom.SetStageUpAxis(stage, up)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    # Ground
    ground = UsdGeom.Plane.Define(stage, "/World/ground")
    ground.CreateAxisAttr(up)
    ground.CreateWidthAttr(10.0)
    ground.CreateLengthAttr(10.0)
    UsdPhysics.CollisionAPI.Apply(ground.GetPrim())

    for obj in scene["objects"]:
        path = f"/World/{_usd_name(obj['id'])}"
        xform = UsdGeom.Xform.Define(stage, path)
        tx, ty, tz = obj["transform"]["translation"]
        xform.AddTranslateOp().Set(Gf.Vec3d(tx, ty, tz))
        qx, qy, qz, qw = obj["transform"]["rotation_quat"]
        xform.AddOrientOp().Set(Gf.Quatd(qw, qx, qy, qz))

        ref = xform.GetPrim().GetReferences()
        ref.AddReference(obj["mesh"])

        UsdPhysics.CollisionAPI.Apply(xform.GetPrim())
        if obj["physics"]["is_rigid"]:
            rb = UsdPhysics.RigidBodyAPI.Apply(xform.GetPrim())
            rb.CreateRigidBodyEnabledAttr(True)
        mass_api = UsdPhysics.MassAPI.Apply(xform.GetPrim())
        mass_api.CreateMassAttr(obj["physics"]["mass_kg"])

    stage.GetRootLayer().Save()
    return out


def _usd_name(name: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name)
