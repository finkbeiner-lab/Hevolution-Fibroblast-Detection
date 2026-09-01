# Running the app locally (same UI, no RunPod account)

`Gradio-RunPod.py` normally posts each image to the RunPod Serverless
endpoint. Setting `LOCAL_INFERENCE=1` makes it call `runpod_handler.handler()`
in the same process instead. **Same UI file, same worker file, same
statistics** — only the transport changes, so what you see locally is what
production does.

```
LOCAL_INFERENCE unset          LOCAL_INFERENCE=1
┌──────────────┐               ┌───────────────────────────┐
│ Gradio UI    │──HTTP──▶ RunPod│ Gradio UI → handler()     │
│ (EC2)        │◀──────── GPU  │ (one process, local GPU/CPU)│
└──────────────┘               └───────────────────────────┘
```

---

## 1. One-time environment setup

The worker uses the **cellpose 3.x** API (`models.Cellpose`). Cellpose 4
renamed that class and ships a different model (Cellpose-SAM), so it will
neither import nor reproduce production numbers. Use a dedicated env rather
than downgrading a shared one:

```bash
conda create -n fibroblast-local python=3.11 -y
conda activate fibroblast-local
pip install -r requirements-local.txt
```

Verify:

```bash
python -c "from cellpose import models; print(models.Cellpose)"
```

## 2. Run it

```bash
./run_local.sh
```

The script activates the `fibroblast-local` env itself, so you don't have to
remember to do it first. Open <http://127.0.0.1:7860>.

> Running `conda activate fibroblast-local` and `./run_local.sh` as a single
> pasted line produces
> `EnvironmentLocationNotFound: Not a conda environment: .../fibroblast-local./run_local.sh`
> — conda sees the `/` and reads the whole string as a path. Keep them on
> separate lines, join them with `&&`, or just run `./run_local.sh` on its own. The left panel shows **Backend: `local
(in-process cellpose)`** so you can tell at a glance which mode you're in.

The first click is slow (~30–60 s): cellpose downloads the `cyto3` weights
(~25 MB) and loads the model. Every click after that reuses the loaded model,
exactly like a warm RunPod worker.

### Diameter sweep

Cellpose is sensitive to the diameter you give it, and the right value is not
obvious from looking at a plate. Switch **Diameter mode** to **Diameter sweep**
to segment the same image once per diameter and compare:

- set the smallest and largest diameter, and how many to try (2–12);
- a line under the sliders previews exactly which diameters will run;
- results come back as a mask gallery (one per diameter), a table of
  cell count and confluency, and a two-panel chart of both against diameter.

Every mask is written to `local-runs/fibroblast/<job_id>/mask_d<diameter>.png`
and the numbers land in `stats.json`, so you can compare runs later.

The highest cell count is **not** automatically the right answer — an
over-small diameter fragments one cell into several, which inflates the count.
Use the gallery to check the masks against the cells you can actually see.

Each diameter is a full segmentation, so a 5-point sweep costs roughly 5x a
single run. That's free locally; on RunPod it is 5x the GPU seconds, which is
exactly why it's worth settling the diameter here first.

### What it writes

`run_local.sh` points `PERSIST_ROOT` at `./local-runs/`, which exercises the
same persistence code the RunPod Network Volume uses:

```
local-runs/fibroblast/<job_id>/
    input.png  normalized.png  mask.png  histogram.png  stats.json
```

Handy for checking that `stats.json` carries the cell line and parameters you
expect before trusting the cloud runs. `local-runs/` is gitignored.

---

## 3. Using a cluster GPU

**No code changes are needed.** `runpod_handler.py` decides at startup with
`torch.cuda.is_available()`, so on a CUDA node it uses the GPU automatically —
the same line that drives the real RunPod worker. `run_local.sh` prints which
device it picked.

Three things differ from a laptop:

**Install the CUDA build of torch.** On Linux, `pip install -r
requirements-local.txt` already pulls a CUDA wheel. Confirm on a GPU node:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

**Pre-seed the model weights if compute nodes have no internet.** Run once on
a login node (which usually does):

```bash
CELLPOSE_LOCAL_MODELS_PATH=$PWD/.cellpose_models \
  python -c "from cellpose import models; models.Cellpose(gpu=False, model_type='cyto3')"
```

`run_local.sh` sets `CELLPOSE_LOCAL_MODELS_PATH` to that folder, so the job
finds them offline. This mirrors how production pre-populates
`/runpod-volume/cellpose_models` (see `Dockerfile.runpod`).

**Reach the UI through an SSH tunnel** — compute nodes are not directly
routable, and you should not expose Gradio on an open port.

### Interactive session

```bash
srun --partition=gpu --gres=gpu:1 --cpus-per-task=8 --mem=32G --time=2:00:00 --pty bash
conda activate fibroblast-local
cd /path/to/Hevolution-Fibroblast-Detection
GRADIO_SERVER_NAME=0.0.0.0 ./run_local.sh
```

Then from your laptop, in a second terminal:

```bash
ssh -N -L 7860:<compute-node-hostname>:7860 <user>@<login-node>
```

Open <http://127.0.0.1:7860>.

### Batch job

`run_cluster_gpu.slurm` does the same thing unattended and prints the exact
tunnel command into its `.out` file:

```bash
sbatch run_cluster_gpu.slurm
tail -f fibroblast-ui-<jobid>.out
```

Edit the `#SBATCH --partition` / `--gres` lines to match your cluster's names.

> Not on SLURM? The only scheduler-specific parts are the `#SBATCH` block and
> the hostname in the tunnel command. The launch step is always
> `GRADIO_SERVER_NAME=0.0.0.0 ./run_local.sh` on a node with a GPU.

---

## 4. Testing against the real RunPod endpoint

Same UI, cloud backend — this is the true pre-deploy check. Leave
`LOCAL_INFERENCE` unset and supply credentials:

```bash
export RUNPOD_API_KEY=rpa_...
export RUNPOD_ENDPOINT_ID=<endpoint-id>
python Gradio-RunPod.py
```

Only `requirements-frontend.txt` is needed for this mode — no torch, no
cellpose.

---

## 5. Headless checks (no browser)

Batch-process a folder with the original CLI, unchanged:

```bash
conda activate fibroblast-local
python detect_fibroblast.py /path/to/images --diameter 30 --model cyto3 --save_dir /path/to/masks
python plot_confluency_batch.py     # edit the paths at the bottom first
```

Or drive the worker directly, the way RunPod does:

```python
from runpod_handler import handler
out = handler({"id": "test-1", "input": {"image_b64": "<base64 png>", "diameter": 30}})
print({k: v for k, v in out.items() if not k.endswith("_b64")})
```

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `AttributeError: module 'cellpose.models' has no attribute 'Cellpose'` | Cellpose 4.x is active. Use the `fibroblast-local` env (cellpose <4). |
| First click takes ~a minute | Normal — weight download + model load. Only once per process. |
| `using CPU` on a GPU node | No CUDA torch wheel, or no GPU allocated. Check `nvidia-smi` and `torch.cuda.is_available()`. |
| Port 7860 in use | `GRADIO_SERVER_PORT=7861 ./run_local.sh` |
| Tunnel connects but page won't load | Job must bind `0.0.0.0`, and tunnel to the *compute node* hostname, not the login node. |
