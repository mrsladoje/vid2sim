#!/usr/bin/env bash
# T-60 min RunPod pre-warm ritual (ADR-009 §operational run-book).
#
# Preconditions:
#   - Pod is started (run `runpod pod start $POD_ID` ahead of this script).
#   - RUNPOD_API_KEY and RUNPOD_ENDPOINT are exported, or config/runpod.yaml
#     has a non-placeholder endpoint URL.
#   - A cached warm-up crop + mask exist at data/warmup/.
#
# Effects:
#   - GET /healthz — confirm pod up and both models discoverable.
#   - POST /mesh (Hunyuan3D) + POST /mesh (TripoSG) — warm both weights
#     into GPU memory so the first real request doesn't pay cold-start.
#   - Prints a three-line summary suitable for the run-book.

set -euo pipefail

ENDPOINT="${RUNPOD_ENDPOINT:-}"
if [ -z "$ENDPOINT" ]; then
  ENDPOINT="$(python3 - <<'PY'
import sys, yaml
with open("config/runpod.yaml") as fh:
    cfg = yaml.safe_load(fh)
print(cfg["endpoint"]["url"])
PY
  )"
fi

if [[ "$ENDPOINT" == *REPLACE_ME* ]]; then
  echo "ERROR: config/runpod.yaml endpoint is still a placeholder." >&2
  echo "Export RUNPOD_ENDPOINT=https://<your-pod>.proxy.runpod.net before running." >&2
  exit 2
fi

CROP="${CROP:-data/warmup/crop.jpg}"
MASK="${MASK:-data/warmup/mask.png}"

if [ ! -f "$CROP" ] || [ ! -f "$MASK" ]; then
  echo "ERROR: warm-up crop/mask missing ($CROP / $MASK)." >&2
  echo "Generate one via scripts/generate_warmup_crop.py before the demo." >&2
  exit 2
fi

echo "== VID2SIM RunPod pre-warm =="
echo "  endpoint: $ENDPOINT"
echo "  crop:     $CROP"
echo "  mask:     $MASK"
echo

echo ">> healthz"
t0=$(python3 -c 'import time; print(time.monotonic())')
HZ_BODY=$(curl -fsS "$ENDPOINT/healthz")
t1=$(python3 -c 'import time; print(time.monotonic())')
printf '  latency: %.0f ms\n' "$(python3 -c "print(($t1-$t0)*1000)")"
echo "  body:    $HZ_BODY"
echo

for MODEL in hunyuan3d triposg; do
  echo ">> warmup /mesh model=$MODEL"
  t0=$(python3 -c 'import time; print(time.monotonic())')
  OUT_FILE="$(mktemp -t vid2sim_warm_${MODEL}.XXXXXX.glb)"
  curl -fsS -o "$OUT_FILE" \
      -F "rgb_crop=@${CROP}" \
      -F "mask=@${MASK}" \
      -F "model=${MODEL}" \
      "$ENDPOINT/mesh"
  t1=$(python3 -c 'import time; print(time.monotonic())')
  SIZE=$(wc -c < "$OUT_FILE")
  printf '  wall_time: %.2f s   glb_size: %s bytes\n' \
      "$(python3 -c "print($t1-$t0)")" "$SIZE"
  rm -f "$OUT_FILE"
done

echo
echo "pod pre-warmed. Keep this terminal open; re-run at T-10 for the final"
echo "health-check before the pitch."
