#!/usr/bin/env bash
# Run the full app locally: the real Gradio UI + the real RunPod worker code,
# with cellpose executing in-process. No RunPod account or API key needed.
#
#   ./run_local.sh              -> http://127.0.0.1:7860
#
# One-time env setup is in LOCAL_TESTING.md.
set -euo pipefail
cd "$(dirname "$0")"

# Run the worker in-process instead of calling the RunPod REST API.
export LOCAL_INFERENCE=1

# Bind to loopback only - this is a dev box, not the EC2 host.
export GRADIO_SERVER_NAME="${GRADIO_SERVER_NAME:-127.0.0.1}"
export GRADIO_SERVER_PORT="${GRADIO_SERVER_PORT:-7860}"

# Exercise the same per-job persistence path the Network Volume provides,
# but write into a local folder instead of /runpod-volume.
export PERSIST_ROOT="${PERSIST_ROOT:-$PWD/local-runs}"
mkdir -p "$PERSIST_ROOT"

export MPLBACKEND=Agg

# Don't phone home from a lab machine.
export GRADIO_ANALYTICS_ENABLED=False

# Cache cellpose weights next to the repo so a shared/offline machine only
# ever downloads them once. Pre-seed on an offline node (see LOCAL_TESTING.md).
export CELLPOSE_LOCAL_MODELS_PATH="${CELLPOSE_LOCAL_MODELS_PATH:-$PWD/.cellpose_models}"
mkdir -p "$CELLPOSE_LOCAL_MODELS_PATH"

python - <<'EOF'
import torch
print("GPU    :", "CUDA " + torch.cuda.get_device_name(0) if torch.cuda.is_available()
      else "none (CPU) - expect ~1-10 s/image")
EOF
echo "UI     : http://${GRADIO_SERVER_NAME}:${GRADIO_SERVER_PORT}"
echo "Artifacts: ${PERSIST_ROOT}/fibroblast/<job_id>/"
exec python Gradio-RunPod.py
