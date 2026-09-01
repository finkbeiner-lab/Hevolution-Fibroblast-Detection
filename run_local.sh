#!/usr/bin/env bash
# Run the full app locally: the real Gradio UI + the real RunPod worker code,
# with cellpose executing in-process. No RunPod account or API key needed.
#
#   ./run_local.sh              -> http://127.0.0.1:7860
#
# One-time env setup is in LOCAL_TESTING.md.
set -euo pipefail
cd "$(dirname "$0")"

# --- Make sure we're in the right conda env -----------------------------
# Activating it here means `./run_local.sh` works on its own; you don't have
# to remember to activate first. Override the name with FIBRO_ENV=... .
ENV_NAME="${FIBRO_ENV:-fibroblast-local}"

if [[ "${CONDA_DEFAULT_ENV:-}" != "$ENV_NAME" ]]; then
    if ! command -v conda >/dev/null 2>&1; then
        echo "ERROR: conda not found on PATH, and the '$ENV_NAME' env is not active." >&2
        exit 1
    fi
    # shellcheck disable=SC1091
    set +u; source "$(conda info --base)/etc/profile.d/conda.sh"; set -u
    if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
        echo "Activating conda env: $ENV_NAME"
        set +u; conda activate "$ENV_NAME"; set -u
    else
        cat >&2 <<MSG
ERROR: conda env '$ENV_NAME' does not exist. Create it once with:

    conda create -n $ENV_NAME python=3.11 -y
    conda activate $ENV_NAME
    pip install -r requirements-local.txt      # cellpose 3 / cyto3
    #   ...or requirements-sam.txt              # cellpose 4 / Cellpose-SAM

See LOCAL_TESTING.md.
MSG
        exit 1
    fi
fi

# The worker runs on either cellpose 3 (models.Cellpose + cyto3) or cellpose 4
# (models.CellposeModel + Cellpose-SAM) and adapts to whichever is installed.
# Fail early only on an inconsistent env, rather than halfway through a click.
python - <<'PYCHK' || exit 1
import sys
try:
    import cellpose
    from cellpose import models
except ImportError:
    sys.exit("ERROR: cellpose is not installed. Install requirements-local.txt "
             "(cellpose 3) or requirements-sam.txt (cellpose 4).")

version = str(cellpose.version)
major = int(version.split(".")[0])
has_v3 = hasattr(models, "Cellpose")
if (major < 4) != has_v3:
    sys.exit(f"ERROR: cellpose {version} reports major {major}, but models.Cellpose "
             f"is {'present' if has_v3 else 'missing'}. This env is inconsistent; "
             "reinstall cellpose.")
print(f"Cellpose: {version} -> "
      + ("cyto3 (diameter-driven)" if has_v3 else "Cellpose-SAM (cpsam)"))
PYCHK

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
# The repo-local cache holds cyto3 only. Cellpose-SAM's cpsam_v2 is 1.2 GB and
# already sits in ~/.cellpose/models, so pointing v4 at the repo cache would
# re-download it onto a network share. Use the home cache for v4.
if [[ -z "${CELLPOSE_LOCAL_MODELS_PATH:-}" ]]; then
    if python -c "from cellpose import models; import sys; \
                  sys.exit(0 if hasattr(models, 'Cellpose') else 1)" 2>/dev/null; then
        CELLPOSE_LOCAL_MODELS_PATH="$PWD/.cellpose_models"
    else
        CELLPOSE_LOCAL_MODELS_PATH="$HOME/.cellpose/models"
    fi
fi
export CELLPOSE_LOCAL_MODELS_PATH
mkdir -p "$CELLPOSE_LOCAL_MODELS_PATH"

python - <<'EOF'
import torch
print("GPU    :", "CUDA " + torch.cuda.get_device_name(0) if torch.cuda.is_available()
      else "none (CPU) - expect ~1-10 s/image")
EOF
echo "UI     : http://${GRADIO_SERVER_NAME}:${GRADIO_SERVER_PORT}"
echo "Artifacts: ${PERSIST_ROOT}/fibroblast/<job_id>/"
exec python Gradio-RunPod.py
