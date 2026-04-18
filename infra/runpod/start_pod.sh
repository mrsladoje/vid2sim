#!/usr/bin/env bash
# VID2SIM pod — post-restart one-command recovery wrapper.
#
# Usage inside the pod (after any RunPod pod restart):
#   bash /workspace/start_pod.sh
#
# This is a thin wrapper over pod_bootstrap.sh so the post-restart ritual
# has a memorable name. All the actual logic lives in pod_bootstrap.sh
# (idempotent: re-installs apt + pip deps, restores authorized_keys from
# /workspace/.ssh/id_ed25519.pub, restarts uvicorn under tmux).

exec bash "$(dirname "$0")/pod_bootstrap.sh" "$@"
