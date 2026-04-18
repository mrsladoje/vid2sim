# RunPod image for VID2SIM Stage B diffusion (ADR-009).
# Primary: Hunyuan3D 2.1. Fallback (same pod): TripoSG 1.5B.
#
# Expectations:
# - Persistent volume at /workspace/weights holds pre-downloaded models.
#   The first pod bring-up primes this volume; subsequent starts reuse it.
# - FastAPI server on :8000 exposes POST /mesh and GET /healthz.
# - No secrets baked into the image; RUNPOD_API_KEY is only used on the
#   client side for pod lifecycle, never inside the image.

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/workspace/weights/hf \
    TORCH_HOME=/workspace/weights/torch \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.11 python3.11-venv python3-pip \
      git wget curl ca-certificates \
      libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/bin/python && \
    python -m pip install --upgrade pip

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

COPY server.py /workspace/server.py
COPY prewarm.py /workspace/prewarm.py

EXPOSE 8000

# Healthcheck piggybacks on the FastAPI /healthz endpoint.
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
