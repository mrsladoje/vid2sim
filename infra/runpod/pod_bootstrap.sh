#!/usr/bin/env bash
# VID2SIM RunPod pod bootstrap — run this INSIDE the pod.
#
# Usage:
#   # Option A: paste this whole file into the pod's web terminal
#   # Option B: from your laptop
#   scp infra/runpod/pod_bootstrap.sh <pod-ssh>:/workspace/
#   ssh <pod-ssh>   # interactive
#   bash /workspace/pod_bootstrap.sh
#
# Idempotent. Re-running is safe — dependencies are skipped if present,
# weights are skipped if already downloaded, server is restarted.

set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
WEIGHTS_DIR="${WEIGHTS_DIR:-$WORKSPACE/weights}"
REPO_DIR="$WORKSPACE/vid2sim"
PORT="${PORT:-8000}"
REPO_URL="${REPO_URL:-https://github.com/mrsladoje/vid2sim.git}"

log() { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[bootstrap ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

log "workspace:  $WORKSPACE"
log "weights:    $WEIGHTS_DIR"
log "repo dir:   $REPO_DIR"
log "port:       $PORT"

# -- 0. Persist the authorized key across pod restarts ----------------------
# RunPod pod restarts wipe the container filesystem (including
# /root/.ssh/authorized_keys) but preserve /workspace/. We store the
# laptop's public key under /workspace/ and re-install it on every boot
# so direct-TCP scp keeps working after restarts without manual steps.
LAPTOP_PUBKEY_STORE="$WORKSPACE/.ssh/id_ed25519.pub"
if [ -f "$LAPTOP_PUBKEY_STORE" ]; then
    mkdir -p /root/.ssh && chmod 700 /root/.ssh
    cat "$LAPTOP_PUBKEY_STORE" >> /root/.ssh/authorized_keys 2>/dev/null || true
    # de-duplicate in case we've re-appended
    sort -u /root/.ssh/authorized_keys -o /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
    log "step 0/6  authorized_keys restored from $LAPTOP_PUBKEY_STORE"
else
    log "step 0/6  no persisted pubkey at $LAPTOP_PUBKEY_STORE"
    log "          (paste one to persist: mkdir -p $WORKSPACE/.ssh && \\"
    log "           echo 'ssh-ed25519 AAA...' > $LAPTOP_PUBKEY_STORE)"
fi

# -- 1. GPU sanity check ------------------------------------------------------
log "step 1/6  gpu probe"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader \
    || die "no CUDA GPU visible — is this a GPU pod?"

# -- 2. Python + core deps ----------------------------------------------------
log "step 2/6  system + python deps"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    git curl wget ca-certificates \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    tmux >/dev/null

python3 -m pip install --upgrade -q pip wheel setuptools

# Use the CUDA 12.4 wheel index matching the pod's driver.
python3 -m pip install -q \
    --extra-index-url https://download.pytorch.org/whl/cu124 \
    torch torchvision

python3 -m pip install -q \
    fastapi 'uvicorn[standard]' python-multipart pydantic>=2.6 \
    numpy Pillow trimesh pygltflib huggingface-hub pyyaml \
    transformers diffusers accelerate safetensors einops

# -- 3. Locate server code ----------------------------------------------------
# Two paths:
#   A. Files have already been scp'd into /workspace/ (private-repo path).
#      Detect by presence of server.py + models_*.py at $WORKSPACE.
#   B. Public repo — clone then copy.
log "step 3/6  stage server code"
if [ -f "$WORKSPACE/server.py" ] && \
   [ -f "$WORKSPACE/models_hunyuan3d.py" ] && \
   [ -f "$WORKSPACE/models_triposg.py" ]; then
    log "  found pre-staged files at $WORKSPACE — skipping git clone"
else
    if [ -d "$REPO_DIR/.git" ]; then
        git -C "$REPO_DIR" fetch --quiet origin main
        git -C "$REPO_DIR" reset --quiet --hard origin/main
    else
        git clone -q "$REPO_URL" "$REPO_DIR" || die \
            "git clone of $REPO_URL failed — if the repo is private, \
scp the files from your laptop instead (see infra/runpod/pod_bootstrap.sh header)."
    fi
    cp "$REPO_DIR/infra/runpod/server.py"            "$WORKSPACE/server.py"
    cp "$REPO_DIR/infra/runpod/models_hunyuan3d.py"  "$WORKSPACE/models_hunyuan3d.py"
    cp "$REPO_DIR/infra/runpod/models_triposg.py"    "$WORKSPACE/models_triposg.py"
    cp "$REPO_DIR/infra/runpod/prewarm.py"           "$WORKSPACE/prewarm.py"
fi

# Shift numbering: steps 4+ keep their original semantics.

# -- 4. Install Hunyuan3D-2.1 and TripoSG-1.5B codebases ----------------------
log "step 4/7  install image-to-3D model packages"
mkdir -p "$WEIGHTS_DIR"
cd "$WEIGHTS_DIR"

# Hunyuan3D 2.1 — reference impl ships the `hy3dshape` + `hy3dpaint` modules.
if [ ! -d "$WEIGHTS_DIR/src/Hunyuan3D-2.1" ]; then
    git clone -q --depth 1 https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git \
        "$WEIGHTS_DIR/src/Hunyuan3D-2.1"
fi
# Install the runtime deps from each repo's requirements.txt.
# We do NOT `pip install -e .` — neither repo ships a root setup.py; the
# Python packages live in subdirs (hy3dshape/, hy3dpaint/, triposg/) and
# are picked up via PYTHONPATH in step 6.
if [ -f "$WEIGHTS_DIR/src/Hunyuan3D-2.1/requirements.txt" ]; then
    python3 -m pip install -q -r "$WEIGHTS_DIR/src/Hunyuan3D-2.1/requirements.txt" \
        || log "  (some hunyuan3d requirements did not pin cleanly — continuing)"
fi

# TripoSG 1.5B
if [ ! -d "$WEIGHTS_DIR/src/TripoSG" ]; then
    git clone -q --depth 1 https://github.com/VAST-AI-Research/TripoSG.git \
        "$WEIGHTS_DIR/src/TripoSG"
fi
if [ -f "$WEIGHTS_DIR/src/TripoSG/requirements.txt" ]; then
    python3 -m pip install -q -r "$WEIGHTS_DIR/src/TripoSG/requirements.txt" \
        || log "  (some triposg requirements did not pin cleanly — continuing)"
fi

# Make both source trees importable without needing setup.py by
# prepending them to PYTHONPATH at server launch time (step 6).
#
# Hunyuan3D-2.1 uses a nested layout (outer hy3dshape/ is a project
# folder; the actual Python package is at hy3dshape/hy3dshape/). The
# same shape holds for hy3dpaint. TripoSG is a normal single-level
# layout — the package is triposg/ at the repo root.
HY3D_SHAPE_PKG="$WEIGHTS_DIR/src/Hunyuan3D-2.1/hy3dshape"
HY3D_PAINT_PKG="$WEIGHTS_DIR/src/Hunyuan3D-2.1/hy3dpaint"
TRIPOSG_PKG="$WEIGHTS_DIR/src/TripoSG"
export POD_PYTHONPATH="$HY3D_SHAPE_PKG:$HY3D_PAINT_PKG:$TRIPOSG_PKG"

# -- 5. Pre-pull HF weights (eager, so first /mesh is warm) -------------------
log "step 5/7  download weights (this is the slow step: 10–20 min)"
export HF_HOME="$WEIGHTS_DIR/hf"
mkdir -p "$HF_HOME"
python3 - <<PY
import os
from huggingface_hub import snapshot_download
os.environ["HF_HOME"] = os.environ.get("HF_HOME", "$WEIGHTS_DIR/hf")
for repo in ("tencent/Hunyuan3D-2.1", "VAST-AI/TripoSG"):
    print(f"  pulling {repo} ...", flush=True)
    snapshot_download(repo_id=repo, cache_dir=os.environ["HF_HOME"],
                      tqdm_class=None)
    print(f"  ✓ {repo}", flush=True)
PY

# -- 6. Launch the FastAPI server under tmux ---------------------------------
log "step 6/6  launch server"
# Kill any previous instance so this script is re-runnable.
tmux kill-session -t vid2sim 2>/dev/null || true
sleep 1

tmux new-session -d -s vid2sim \
    "cd $WORKSPACE && \
     HF_HOME=$HF_HOME \
     WEIGHTS_DIR=$WEIGHTS_DIR \
     PYTHONPATH=\"${POD_PYTHONPATH:-}:\${PYTHONPATH:-}\" \
     VID2SIM_POD_INFERENCE=1 \
     uvicorn server:app --host 0.0.0.0 --port $PORT 2>&1 | tee -a $WORKSPACE/server.log"

sleep 4
log "healthz probe:"
curl -fsS "http://127.0.0.1:$PORT/healthz" \
    || die "server is not answering on :$PORT — check tmux (tmux attach -t vid2sim)"
echo

log "server running under tmux session 'vid2sim'."
log "to tail logs:      tmux attach -t vid2sim    (Ctrl-B then D to detach)"
log "to stop server:    tmux kill-session -t vid2sim"
log ""
log "external endpoint (copy into config/runpod.yaml on your laptop):"
if [ -n "${RUNPOD_POD_ID:-}" ]; then
    log "  https://${RUNPOD_POD_ID}-${PORT}.proxy.runpod.net"
else
    log "  https://<POD_ID>-${PORT}.proxy.runpod.net   (fill POD_ID from RunPod dashboard)"
fi
