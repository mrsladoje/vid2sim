#!/usr/bin/env bash
# VID2SIM RunPod pod bootstrap — run this INSIDE the pod.
#
# Usage (pod shell):
#   bash /workspace/pod_bootstrap.sh
#   # or via the wrapper:
#   bash /workspace/start_pod.sh
#
# Idempotent. Designed to minimise restart cost.
#
# What survives a RunPod restart (reused here):
#   /workspace/venv/           (persistent Python venv — all pip deps)
#   /workspace/weights/        (HF models + source repos)
#   /workspace/server.py etc.  (scp'd in once)
#   /workspace/.ssh/id_ed25519.pub  (laptop pubkey)
# What the script handles on every run:
#   apt packages (~30s — can't persist; tiny anyway)
#   venv creation on first run; reuse on subsequent runs (~2s)
#   pip installs only when the venv is new (or MISSING_DEPS is listed)
#   authorized_keys restoration (so scp keeps working)
#   tmux + uvicorn restart

set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
WEIGHTS_DIR="${WEIGHTS_DIR:-$WORKSPACE/weights}"
VENV_DIR="${VENV_DIR:-$WORKSPACE/venv}"
REPO_DIR="$WORKSPACE/vid2sim"
PORT="${PORT:-8000}"
REPO_URL="${REPO_URL:-https://github.com/mrsladoje/vid2sim.git}"

log() { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[bootstrap ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

log "workspace:  $WORKSPACE"
log "weights:    $WEIGHTS_DIR"
log "venv:       $VENV_DIR"
log "port:       $PORT"

# -- 0c. Auto-load HF token from /workspace/.hf/token if present -------------
# Some HF repos (e.g. stabilityai/stable-fast-3d) are gated — they need
# auth headers on every request. Persist the user's read token under
# /workspace and export it on boot so snapshot_download + the model
# loaders authenticate transparently.
if [ -f "$WORKSPACE/.hf/token" ]; then
    HF_TOKEN_VAL="$(cat "$WORKSPACE/.hf/token")"
    export HF_TOKEN="$HF_TOKEN_VAL"
    export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN_VAL"
fi

# -- 0b. Persist library caches onto /workspace ------------------------------
# Several model libraries (notably hy3dgen/hy3dshape) ignore cache_dir=
# kwargs and write into /root/.cache/, which is ephemeral. Symlink them
# into /workspace/cache/ so their internal downloads persist across pod
# restarts. Idempotent — safe to rerun.
mkdir -p "$WORKSPACE/cache" /root/.cache
for libdir in hy3dgen huggingface torch; do
    target="$WORKSPACE/cache/$libdir"
    link="/root/.cache/$libdir"
    mkdir -p "$target"
    if [ -d "$link" ] && [ ! -L "$link" ]; then
        # Existing real dir — migrate its contents to /workspace once
        cp -an "$link"/. "$target"/ 2>/dev/null || true
        rm -rf "$link"
    fi
    ln -sfn "$target" "$link"
done

# -- 0. Persist the authorized key across pod restarts ----------------------
# RunPod pod restarts wipe the container filesystem (including
# /root/.ssh/authorized_keys) but preserve /workspace/. We store the
# laptop's public key under /workspace/ and re-install it on every boot.
LAPTOP_PUBKEY_STORE="$WORKSPACE/.ssh/id_ed25519.pub"
if [ -f "$LAPTOP_PUBKEY_STORE" ]; then
    mkdir -p /root/.ssh && chmod 700 /root/.ssh
    touch /root/.ssh/authorized_keys
    cat "$LAPTOP_PUBKEY_STORE" >> /root/.ssh/authorized_keys 2>/dev/null || true
    sort -u /root/.ssh/authorized_keys -o /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
    log "step 0/6  authorized_keys restored from $LAPTOP_PUBKEY_STORE"
else
    log "step 0/6  no persisted pubkey at $LAPTOP_PUBKEY_STORE (scp will break on restart)"
fi

# -- 1. GPU sanity check ------------------------------------------------------
log "step 1/6  gpu probe"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader \
    || die "no CUDA GPU visible — is this a GPU pod?"

# -- 2a. Pin pip to pypi.org (some RunPod templates default to an aliyun
#       mirror which is slow from EU/US regions). Persisted under
#       /workspace so it survives restarts; also written to /root for
#       the container's system pip.
PIP_CONF_PERSISTED="$WORKSPACE/.pip/pip.conf"
if [ ! -f "$PIP_CONF_PERSISTED" ]; then
    mkdir -p "$WORKSPACE/.pip"
    cat > "$PIP_CONF_PERSISTED" <<'PIPCONF'
[global]
index-url = https://pypi.org/simple/
extra-index-url = https://download.pytorch.org/whl/cu124
timeout = 120
PIPCONF
fi
mkdir -p /root/.pip
cp "$PIP_CONF_PERSISTED" /root/.pip/pip.conf

# -- 2. APT deps (ephemeral; re-install every run, ~30s) ---------------------
log "step 2/6  system deps (apt)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    git curl wget ca-certificates python3-venv tmux \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    libxi6 libxxf86vm1 libxfixes3 libxkbcommon0 libx11-6 \
    libxrandr2 libxinerama1 libxcursor1 libegl1 libgomp1 \
    >/dev/null

# -- 3. Persistent Python venv on /workspace ---------------------------------
# First run: create venv + install everything (~4 min total, one-time).
# Subsequent runs: just activate (~1 s). Deps persist across pod restarts.
PYBIN="$VENV_DIR/bin/python"
PIPBIN="$VENV_DIR/bin/pip"
VENV_STAMP="$VENV_DIR/.vid2sim_deps_installed"

if [ ! -x "$PYBIN" ]; then
    log "step 3/6  creating persistent venv at $VENV_DIR (first run only)"
    python3 -m venv "$VENV_DIR"
    "$PIPBIN" install --upgrade -q pip wheel setuptools
else
    log "step 3/6  reusing persistent venv at $VENV_DIR"
fi

if [ ! -f "$VENV_STAMP" ]; then
    log "  installing pip deps into venv (one-time cost — ~4 min)"

    # CUDA 12.4 torch wheel
    "$PIPBIN" install -q \
        --extra-index-url https://download.pytorch.org/whl/cu124 \
        torch torchvision

    # Core server + generic ML deps
    "$PIPBIN" install -q \
        fastapi 'uvicorn[standard]' python-multipart 'pydantic>=2.6' \
        numpy Pillow trimesh pygltflib huggingface-hub pyyaml \
        transformers diffusers accelerate safetensors einops

    # Clone model source repos (persistent under /workspace/weights/src/)
    mkdir -p "$WEIGHTS_DIR/src"
    if [ ! -d "$WEIGHTS_DIR/src/Hunyuan3D-2.1" ]; then
        git clone -q --depth 1 https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git \
            "$WEIGHTS_DIR/src/Hunyuan3D-2.1"
    fi
    if [ ! -d "$WEIGHTS_DIR/src/TripoSG" ]; then
        git clone -q --depth 1 https://github.com/VAST-AI-Research/TripoSG.git \
            "$WEIGHTS_DIR/src/TripoSG"
    fi
    if [ ! -d "$WEIGHTS_DIR/src/stable-fast-3d" ]; then
        git clone -q --depth 1 https://github.com/Stability-AI/stable-fast-3d.git \
            "$WEIGHTS_DIR/src/stable-fast-3d"
    fi
    if [ ! -d "$WEIGHTS_DIR/src/Depth-Anything-3" ]; then
        git clone -q --depth 1 https://github.com/ByteDance-Seed/Depth-Anything-3.git \
            "$WEIGHTS_DIR/src/Depth-Anything-3"
    fi
    # DA3 ships as a Python package — install it editable so the
    # `depth_anything_3` import resolves.
    (cd "$WEIGHTS_DIR/src/Depth-Anything-3" && \
        "$PIPBIN" install --no-build-isolation -q -e . \
        || log "  (Depth-Anything-3 editable install warned)")

    # Install each repo's requirements.txt, filtering out pins that abort
    # pip (bpy==4.0 not available on PyPI for py3.11; diso needs no-build
    # -isolation once torch is present).
    _install_filtered_reqs () {
        local reqs="$1"
        [ -f "$reqs" ] || return 0
        local tmp; tmp="$(mktemp)"
        grep -vE '^(bpy|diso)([<>=! ]|$)' "$reqs" > "$tmp" || true
        "$PIPBIN" install -q -r "$tmp" \
            || log "  (some pins in $reqs did not resolve — continuing with what did)"
        rm -f "$tmp"
    }
    _install_filtered_reqs "$WEIGHTS_DIR/src/Hunyuan3D-2.1/requirements.txt"
    _install_filtered_reqs "$WEIGHTS_DIR/src/TripoSG/requirements.txt"
    _install_filtered_reqs "$WEIGHTS_DIR/src/stable-fast-3d/requirements.txt"

    # Pure-Python safety net for deps the model code imports transitively
    # but that may have been dropped if requirements.txt install aborted.
    "$PIPBIN" install -q \
        omegaconf einops rembg onnxruntime opencv-python-headless \
        pymeshlab scikit-image pyyaml "pydantic>=2.6" \
        || log "  (some pure-python fallbacks warn but installed)"

    # diso: build against the venv's torch with --no-build-isolation.
    "$PIPBIN" install -q --no-build-isolation diso \
        || log "  (diso build failed — Paint pipeline may fall back)"

    # bpy (Blender Python API) — needed by hy3dpaint.textureGenPipeline
    # for UV unwrap + PBR texture baking. The hunyuan3d requirements
    # pinned bpy==4.0 which isn't on PyPI for py3.11; install the newest
    # compatible version and tolerate failure (untextured meshes still
    # serve).
    "$PIPBIN" install -q 'bpy>=4.2' \
        || log "  (bpy install failed — meshes will be untextured)"

    touch "$VENV_STAMP"
    log "  ✓ venv dep install complete (future restarts skip this step)"
else
    log "  venv already provisioned (stamp: $VENV_STAMP) — skipping pip"
fi

# -- 4. Stage server code -----------------------------------------------------
log "step 4/6  stage server code"
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
            "git clone of $REPO_URL failed — if the repo is private, scp the files in"
    fi
    cp "$REPO_DIR/infra/runpod/server.py"            "$WORKSPACE/server.py"
    cp "$REPO_DIR/infra/runpod/models_hunyuan3d.py"  "$WORKSPACE/models_hunyuan3d.py"
    cp "$REPO_DIR/infra/runpod/models_triposg.py"    "$WORKSPACE/models_triposg.py"
    cp "$REPO_DIR/infra/runpod/prewarm.py"           "$WORKSPACE/prewarm.py"
fi

# Compute PYTHONPATH for the nested Hunyuan3D packages + TripoSG.
HY3D_ROOT="$WEIGHTS_DIR/src/Hunyuan3D-2.1"
SF3D_ROOT="$WEIGHTS_DIR/src/stable-fast-3d"
POD_PYTHONPATH="$HY3D_ROOT/hy3dshape:$HY3D_ROOT/hy3dpaint:$HY3D_ROOT:$WEIGHTS_DIR/src/TripoSG:$SF3D_ROOT"

# -- 5. Pre-pull HF weights (cached — skipped on restart) --------------------
log "step 5/6  download weights (skipped if cached)"
export HF_HOME="$WEIGHTS_DIR/hf"
mkdir -p "$HF_HOME"
"$PYBIN" - <<PY
import os
from huggingface_hub import snapshot_download
os.environ["HF_HOME"] = os.environ.get("HF_HOME", "$WEIGHTS_DIR/hf")
for repo in ("tencent/Hunyuan3D-2.1", "VAST-AI/TripoSG",
             "stabilityai/stable-fast-3d"):
    print(f"  pulling {repo} ...", flush=True)
    snapshot_download(repo_id=repo, cache_dir=os.environ["HF_HOME"],
                      tqdm_class=None)
    print(f"  ✓ {repo}", flush=True)
PY

# -- 6. Launch uvicorn under tmux (using the venv's python) ------------------
log "step 6/6  launch server (venv: $VENV_DIR)"
tmux kill-session -t vid2sim 2>/dev/null || true
sleep 1

tmux new-session -d -s vid2sim \
    "cd $WORKSPACE && \
     HF_HOME=$HF_HOME \
     WEIGHTS_DIR=$WEIGHTS_DIR \
     PYTHONPATH=\"$POD_PYTHONPATH:\${PYTHONPATH:-}\" \
     VID2SIM_POD_INFERENCE=1 \
     $VENV_DIR/bin/uvicorn server:app --host 0.0.0.0 --port $PORT \
       2>&1 | tee -a $WORKSPACE/server.log"

sleep 4
log "healthz probe:"
curl -fsS "http://127.0.0.1:$PORT/healthz" \
    || die "server not answering on :$PORT — tmux attach -t vid2sim to debug"
echo

log ""
log "ready. tmux: tmux attach -t vid2sim   (detach: Ctrl-B then D)"
log "endpoint: https://\${RUNPOD_POD_ID:-<POD_ID>}-${PORT}.proxy.runpod.net"
