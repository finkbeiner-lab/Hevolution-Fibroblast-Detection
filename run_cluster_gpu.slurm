#!/usr/bin/env bash
# Run the local-mode app on a cluster GPU node under SLURM.
#
#   sbatch run_cluster_gpu.slurm
#   # then follow the SSH tunnel command printed in the job's .out file
#
# Adjust the #SBATCH lines to your cluster's partition / QOS names.
#SBATCH --job-name=fibroblast-ui
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=fibroblast-ui-%j.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$PWD}"

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate fibroblast-local

# Pick a free-ish port derived from the job id so concurrent jobs don't clash.
PORT=$(( 7860 + (${SLURM_JOB_ID:-0} % 1000) ))

cat <<MSG
============================================================
 Fibroblast UI on $(hostname), port ${PORT}
 From your laptop:
   ssh -N -L ${PORT}:$(hostname):${PORT} <user>@<login-node>
 Then open:
   http://127.0.0.1:${PORT}
============================================================
MSG

nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

# Bind to all interfaces so the login node can reach it through the tunnel.
GRADIO_SERVER_NAME=0.0.0.0 GRADIO_SERVER_PORT="${PORT}" ./run_local.sh
