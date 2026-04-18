import os
import json
import time
from pathlib import Path
import random

# We create fake data. To emulate images quickly and cleanly without heavy deps like cv2 or PIL, 
# we'll write small valid 1x1 black images.

# 1x1 white JPG
DUMMY_JPG = bytes.fromhex(
    "ffd8ffe000104a46494600010101004800480000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d0d1832211c213232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232ffc00011080001000103012200021101031101ffc4001f0000010501010101010100000000000000000102030405060708090affc400b5100002010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffc4001f0100030101010101010101010000000000000102030405060708090affc400b51100020102040403040705040400010277000102031104052131061241510761711322328108144291a1b1c109233352f0156272d10a162434e125f11718191a262728292a35363738393a434445464748494a535455565758595a636465666768696a737475767778797a82838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c03010002110311003f00f9202020202020af3f"
)
# 1x1 black PNG
DUMMY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da6364606060000000050001e52614a30000000049454e44ae426082"
)

def generate_stub(outdir: str, num_frames: int = 15): # 1 second at 15fps
    path = Path(outdir)
    frames_path = path / "frames"
    frames_path.mkdir(parents=True, exist_ok=True)
    
    # 1. Manifest
    manifest = {
        "session_id": "stub_01",
        "device_serial": "mock_serial",
        "firmware_version": "mock_fw",
        "capture_fps": 15,
        "frame_count": num_frames,
        "class_prompts": ["chair", "table"],
        "timebase_ns": int(time.time() * 1e9)
    }
    with open(path / "capture_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
        
    # 2. Intrinsics
    intrinsics = {
        "camera_matrix": [
            [800.0, 0.0, 960.0],
            [0.0, 800.0, 540.0],
            [0.0, 0.0, 1.0]
        ],
        "resolution": [1920, 1080],
        "baseline_m": 0.075
    }
    with open(path / "intrinsics.json", "w") as f:
        json.dump(intrinsics, f, indent=2)
        
    # 3. Frames
    t_start = manifest["timebase_ns"]
    for i in range(num_frames):
        prefix = f"{i:05d}"
        t_curr = t_start + int(i * (1/15) * 1e9)
        
        with open(frames_path / f"{prefix}.rgb.jpg", "wb") as f:
            f.write(DUMMY_JPG)
            
        for p in ["depth", "conf", "mask_class", "mask_track"]:
            with open(frames_path / f"{prefix}.{p}.png", "wb") as f:
                f.write(DUMMY_PNG)
                
        pose = {
            "translation": [0.0, 0.0, 0.0],
            "rotation_quat": [0.0, 0.0, 0.0, 1.0]
        }
        with open(frames_path / f"{prefix}.pose.json", "w") as f:
            json.dump(pose, f, indent=2)
            
        with open(frames_path / f"{prefix}.imu.jsonl", "w") as f:
            f.write(json.dumps({"timestamp_ns": t_curr, "accel": [0, -9.8, 0], "gyro": [0, 0, 0]}) + "\n")
            
        objs = [
            {
                "track_id": 1,
                "class": "chair",
                "bbox2d": [100, 100, 200, 200],
                "bbox3d": {"center": [0, 1, 2], "size": [0.5, 0.5, 0.5]},
                "conf": 0.95
            }
        ]
        with open(frames_path / f"{prefix}.objects.json", "w") as f:
            json.dump(objs, f, indent=2)

if __name__ == "__main__":
    generate_stub("data/captures/stub_01", 150) # 10s at 15fps
    print("Generated stub capture in data/captures/stub_01")
