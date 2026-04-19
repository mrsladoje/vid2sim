"""Debug viewer for a VID2SIM perception bundle.

Renders, for a selected frame:
- annotated RGB (bbox + mask overlay + class/track/conf labels)
- colourised depth heatmap
- per-object cutout using mask_track

Also unprojects the depth map into a coloured PLY pointcloud (full scene
and per-object cutouts) so we can inspect stereo + mask quality in 3D.

All artifacts land in `<bundle>/_debug/` — they are cheap to regenerate
and must NOT be committed to the bundle (add to .gitignore if needed).

Usage:
    python scripts/view_capture.py data/captures/rec_01
    python scripts/view_capture.py data/captures/rec_01 --frame 25
    python scripts/view_capture.py data/captures/rec_01 --frame 25 --no-open
"""
from __future__ import annotations

import argparse
import colorsys
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]


def _palette_bgr(tid: int) -> tuple[int, int, int]:
    """Distinct BGR colour per track id — HSV evenly spaced, converted."""
    h = (tid * 0.381) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.85, 0.95)
    return (int(b * 255), int(g * 255), int(r * 255))


def colourise_depth(depth_mm: np.ndarray, max_mm: int = 4000) -> np.ndarray:
    d = np.clip(depth_mm, 0, max_mm).astype(np.float32) / max_mm
    d8 = (d * 255).astype(np.uint8)
    d8[depth_mm == 0] = 0
    vis = cv2.applyColorMap(d8, cv2.COLORMAP_TURBO)
    vis[depth_mm == 0] = (0, 0, 0)
    return vis


def annotate_rgb(rgb: np.ndarray, mask_trk: np.ndarray, objects: list[dict]) -> np.ndarray:
    """RGB with coloured mask overlay + bboxes + labels per detected object."""
    out = rgb.copy()
    overlay = out.copy()
    for obj in objects:
        tid = obj["track_id"]
        colour = _palette_bgr(tid)
        overlay[mask_trk == tid] = colour
    out = cv2.addWeighted(overlay, 0.45, out, 0.55, 0)

    for obj in objects:
        tid = obj["track_id"]
        cls = obj["class"]
        conf = obj["conf"]
        x0, y0, x1, y1 = [int(v) for v in obj["bbox2d"]]
        colour = _palette_bgr(tid)
        cv2.rectangle(out, (x0, y0), (x1, y1), colour, 3)
        label = f"[{tid}] {cls} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        cv2.rectangle(out, (x0, max(0, y0 - th - 12)), (x0 + tw + 8, y0), colour, -1)
        cv2.putText(out, label, (x0 + 4, max(th, y0 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
    return out


def unproject_pointcloud(
    depth_mm: np.ndarray, rgb: np.ndarray, K: np.ndarray, stride: int = 2,
    mask: np.ndarray | None = None, max_depth_mm: int = 8000,
) -> tuple[np.ndarray, np.ndarray]:
    """Depth + intrinsics + RGB -> (Nx3 points in metres, Nx3 uint8 colours).

    `stride > 1` subsamples pixels for cheaper previews. Points with
    depth == 0 or depth > max_depth_mm are dropped (invalid stereo).
    Optional `mask` (bool) restricts output to masked pixels only.
    """
    h, w = depth_mm.shape
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    ys, xs = np.meshgrid(np.arange(0, h, stride), np.arange(0, w, stride), indexing="ij")
    d = depth_mm[::stride, ::stride]
    valid = (d > 0) & (d <= max_depth_mm)
    if mask is not None:
        valid &= mask[::stride, ::stride].astype(bool)
    z = d[valid].astype(np.float32) / 1000.0
    x = (xs[valid] - cx) * z / fx
    y = (ys[valid] - cy) * z / fy
    pts = np.stack([x, y, z], axis=-1)
    rgb_sub = rgb[::stride, ::stride][valid]
    # rgb array is BGR from cv2 imread, so swap to RGB for PLY convention
    cols = rgb_sub[:, ::-1].astype(np.uint8)
    return pts, cols


def write_ply(path: Path, pts: np.ndarray, cols: np.ndarray) -> None:
    """Minimal ASCII PLY writer (so we don't pull a heavy dep)."""
    assert pts.shape[0] == cols.shape[0]
    with path.open("w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {pts.shape[0]}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write("end_header\n")
        for (x, y, z), (r, g, b) in zip(pts, cols):
            f.write(f"{x:.4f} {y:.4f} {z:.4f} {int(r)} {int(g)} {int(b)}\n")


def summarise_frame(objects: list[dict], depth_mm: np.ndarray,
                    mask_trk: np.ndarray, K: np.ndarray) -> str:
    lines = [f"Objects: {len(objects)}"]
    for obj in objects:
        tid = obj["track_id"]
        cls = obj["class"]
        conf = obj["conf"]
        x0, y0, x1, y1 = [int(v) for v in obj["bbox2d"]]
        pixels = int((mask_trk == tid).sum())
        # median depth under the mask gives a rough centroid range
        mask_depths = depth_mm[mask_trk == tid]
        mask_depths = mask_depths[mask_depths > 0]
        if mask_depths.size:
            median_mm = float(np.median(mask_depths))
            range_str = f"median={median_mm/1000:.2f}m  min={mask_depths.min()/1000:.2f}m  max={mask_depths.max()/1000:.2f}m"
        else:
            range_str = "NO VALID DEPTH UNDER MASK"
        lines.append(
            f"  [{tid}] {cls:<14} conf={conf:.2f}  bbox=({x0},{y0})->({x1},{y1})  "
            f"mask_px={pixels:>6}  depth: {range_str}"
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("bundle", type=Path, help="path to capture bundle dir")
    ap.add_argument("--frame", type=int, default=None,
                    help="frame index to inspect (default: middle frame)")
    ap.add_argument("--stride", type=int, default=2,
                    help="pixel stride for pointcloud unprojection (higher = fewer points)")
    ap.add_argument("--no-open", action="store_true",
                    help="skip opening the composite PNG in Preview")
    args = ap.parse_args()

    bundle = args.bundle
    frames_dir = bundle / "frames"
    intrinsics_path = bundle / "intrinsics.json"
    if not frames_dir.exists() or not intrinsics_path.exists():
        print(f"ERROR: {bundle} does not look like a capture bundle", file=sys.stderr)
        return 2

    # Pick frame — default to the middle of the bundle.
    rgb_files = sorted(frames_dir.glob("*.rgb.jpg"))
    if not rgb_files:
        print(f"ERROR: no rgb frames under {frames_dir}", file=sys.stderr)
        return 2
    if args.frame is None:
        args.frame = len(rgb_files) // 2
    idx = f"{args.frame:05d}"
    rgb_path = frames_dir / f"{idx}.rgb.jpg"
    if not rgb_path.exists():
        print(f"ERROR: no frame {idx} in {frames_dir} (have 0..{len(rgb_files)-1})", file=sys.stderr)
        return 2

    # Load everything for this frame.
    rgb = cv2.imread(str(rgb_path), cv2.IMREAD_COLOR)
    depth = np.array(Image.open(frames_dir / f"{idx}.depth.png"))
    conf = np.array(Image.open(frames_dir / f"{idx}.conf.png"))
    mask_cls = np.array(Image.open(frames_dir / f"{idx}.mask_class.png"))
    mask_trk = np.array(Image.open(frames_dir / f"{idx}.mask_track.png"))
    objects = json.loads((frames_dir / f"{idx}.objects.json").read_text())
    K = np.array(json.load(intrinsics_path.open())["camera_matrix"], dtype=np.float64)

    debug_dir = bundle / "_debug"
    debug_dir.mkdir(exist_ok=True)

    # Console report.
    summary = summarise_frame(objects, depth, mask_trk, K)
    print(f"=== {bundle.name} / frame {idx} ===")
    print(f"RGB     : {rgb.shape} {rgb.dtype}")
    print(f"Depth   : {depth.shape} {depth.dtype}  valid={float((depth>0).mean())*100:.1f}%  max={int(depth.max())}mm")
    print(f"Conf    : {conf.shape} {conf.dtype}  mean={float(conf.mean()):.1f}")
    unique_cls = sorted(int(c) for c in np.unique(mask_cls) if c != 0)
    cls_names = [COCO_CLASSES[c-1] if 0 < c <= len(COCO_CLASSES) else f"?{c}" for c in unique_cls]
    print(f"Mask cls: ids={unique_cls} names={cls_names}  covered={float((mask_cls>0).mean())*100:.2f}%")
    unique_trk = sorted(int(t) for t in np.unique(mask_trk) if t != 0)
    print(f"Mask trk: ids={unique_trk}  covered={float((mask_trk>0).mean())*100:.2f}%")
    print(summary)

    # Annotated RGB + depth heatmap → composite image.
    annotated = annotate_rgb(rgb, mask_trk, objects)
    depth_vis = colourise_depth(depth)
    # Stack horizontally, scaled down to display-friendly width.
    target_w = 1280
    scale = target_w / annotated.shape[1]
    disp_ann = cv2.resize(annotated, (target_w, int(annotated.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    disp_dep = cv2.resize(depth_vis, (target_w, int(depth_vis.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    composite = np.vstack([disp_ann, disp_dep])
    cv2.putText(composite, f"{bundle.name} / frame {idx} - RGB + masks (top) / depth (bottom)",
                (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    composite_path = debug_dir / f"frame_{idx}_composite.png"
    cv2.imwrite(str(composite_path), composite)
    cv2.imwrite(str(debug_dir / f"frame_{idx}_annotated.png"), annotated)
    cv2.imwrite(str(debug_dir / f"frame_{idx}_depth.png"), depth_vis)

    # Full-scene pointcloud.
    pts, cols = unproject_pointcloud(depth, rgb, K, stride=args.stride)
    scene_ply = debug_dir / f"frame_{idx}_scene.ply"
    write_ply(scene_ply, pts, cols)
    print(f"\nScene pointcloud: {pts.shape[0]:,} points → {scene_ply}")

    # Per-object pointclouds (tint with palette colour for easy viewing).
    for obj in objects:
        tid = obj["track_id"]
        m = (mask_trk == tid)
        o_pts, o_cols = unproject_pointcloud(depth, rgb, K, stride=1, mask=m)
        if o_pts.shape[0] == 0:
            print(f"  [{tid}] {obj['class']}: no valid depth pixels under mask (skipping PLY)")
            continue
        tint = np.array(_palette_bgr(tid)[::-1], dtype=np.uint8)  # BGR -> RGB
        o_cols = ((o_cols.astype(np.int32) + tint.astype(np.int32)) // 2).astype(np.uint8)
        obj_ply = debug_dir / f"frame_{idx}_obj{tid}_{obj['class'].replace(' ','_')}.ply"
        write_ply(obj_ply, o_pts, o_cols)
        centroid = o_pts.mean(axis=0)
        print(f"  [{tid}] {obj['class']}: {o_pts.shape[0]:,} points, centroid (camera frame) "
              f"= [{centroid[0]:+.2f}, {centroid[1]:+.2f}, {centroid[2]:+.2f}] m → {obj_ply.name}")

    print(f"\nComposite PNG   : {composite_path}")
    print(f"Debug directory : {debug_dir}")
    if not args.no_open and sys.platform == "darwin":
        # macOS: open composite in Preview, open the debug dir in Finder.
        subprocess.run(["open", str(composite_path)], check=False)
        subprocess.run(["open", str(debug_dir)], check=False)
        print("\nOpened composite PNG in Preview and _debug/ in Finder.")
        print("PLY files: drag them into MeshLab, or `pip install open3d` and run:")
        print(f"  python -c \"import open3d as o3d; o3d.visualization.draw([o3d.io.read_point_cloud('{scene_ply}')])\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
