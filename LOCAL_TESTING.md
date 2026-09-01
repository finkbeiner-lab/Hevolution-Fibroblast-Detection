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

### Automatic diameter (default)

**Diameter mode → Automatic** sets no diameter at all. The worker scans a grid
of diameters (30–180 px, then refines around the winner, ~10 segmentations)
and keeps the one whose instance masks best reproduce the confluency measured
from image texture.

Confluency never touches Cellpose, so it is an *independent* estimate of how
much of the field is cells. The diameter whose masks come closest to it is the
one to keep. Maximising mask coverage alone would instead reward a diameter
that floods the field with spurious masks — the two rules agree on 7 of the 8
saved images anyway, and where they differ the agreement rule is the safer one.

The plot and table below the result show every diameter tried, so the choice is
auditable rather than magic. Validation on a dense monolayer: the search picked
30 px and captured 32.4%, against 32.5% for the hand-tuned best — it reproduces
the manual optimum without being told.

Cost is the catch: ~10 segmentations instead of one. Larger diameters are
cheaper (Cellpose downscales more), so it is not 10x — measured 21–130 s on
Apple MPS, and far less on a RunPod GPU. Use **Single diameter** when you
already know the value.

### Which model: cyto3 or Cellpose-SAM

The worker adapts to whichever cellpose is installed — `models.Cellpose` +
`cyto3` on v3, `models.CellposeModel` + `cpsam_v2` on v4 — behind one
`_segment()` seam. Two conda envs, because cellpose 3 and 4 cannot coexist:

```bash
./run_local.sh                     # fibroblast-local  -> cellpose 3 / cyto3
FIBRO_ENV=fibroblast-sam ./run_local.sh   # cellpose 4 / Cellpose-SAM
```

Measured in automatic mode on the saved runs (confluency is identical under
both, as it must be — it is a texture measurement independent of the model):

| image | confluency | cyto3 | Cellpose-SAM |
|---|---|---|---|
| confluent swirl | 99.2% | d=30, 206 cells, 3.6% | d=90, 418 cells, **9.3%** |
| dense monolayer | 99.9% | d=30, 1380 cells, **32.4%** | d=128, 848 cells, 30.5% |
| sparse spindly | 30.9% | d=188, 40 cells, 16.0% | d=195, 119 cells, **31.4%** |
| mid density | 55.4% | d=90, 82 cells, 17.8% | d=45, 770 cells, **40.0%** |

Cellpose-SAM wins on three of four, decisively on the sparse and mid-density
fields; cyto3 edges it on the dense monolayer.

> **Cellpose-SAM is not diameter-free**, despite being SAM-based. Measured: at
> `diameter=None` it is its own *worst* setting on every image tried (6.7% vs
> 34.1% on the sparse field), and two of eight images collapse to **zero
> cells** at 180 px. The `diameter` argument survives in v4 as the rescale
> factor; what it lost is v3's size model to guess it. That is the whole reason
> the automatic search exists rather than a plain diameter-free call.
>
> The best diameter is also *not* the cell size — on a confluent field of
> ~25–30 px cells the best setting was 90 px. It is a scale knob, so it has to
> be searched, not estimated.

**Neither model solves the confluent monolayer.** 9.3% captured on a field that
measures 99.2% covered is a large improvement on cyto3's 3.6%, but it is not a
working result. That case is still open.

### Sizing the diameter by hand

The upload panel shows a **preview with a diameter guide**: the image, contrast
stretched the same way the worker normalizes it, with a yellow ring drawn at
the exact pixel diameter Cellpose would be given. Move the slider and the ring
resizes live — no segmentation runs. Pick the value where a ring covers a
typical cell and you have a sensible starting diameter before spending any GPU
time. In sweep mode every diameter in the sweep is drawn, side by side, as a
size ruler across the image.

Large images are shown scaled down; the rings scale with them, so a ring always
means the same thing relative to the cells. The caption says the scale factor
when that happens.

### Diameter sweep

Cellpose is sensitive to the diameter you give it, and the right value is not
obvious from looking at a plate. Switch **Diameter mode** to **Diameter sweep**
to segment the same image once per diameter and compare:

- set the smallest and largest diameter (up to 200 px), and how many to try (2–12);
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

### Image formats and bit depth

Any format PIL can read is accepted — JPEG, PNG, **TIFF (8/16/32-bit, including
multi-page)**, BMP, WebP. The file is sent to the worker **exactly as uploaded**,
so bit depth survives; only images too large for the request limit are decoded
and downscaled (and the log says so, because pixel diameters scale with it).

Multi-page TIFFs — z-stacks, time series — use the first frame.

> Uploads use `gr.File`, not `gr.Image`, on purpose. `gr.Image` converts to
> 8-bit RGB by default, which turns a 16-bit TIFF into solid white and segments
> to nothing with no error; and browsers cannot display TIFF at all, so the
> widget showed an empty box even when the file was fine — the image appeared
> in the results but never at the upload control. `gr.File` passes the bytes
> through untouched, and the diameter-guide preview below it renders a PNG the
> browser can actually show. Don't swap it back.

### How confluency is measured

Confluency is **not** derived from the Cellpose masks. It is measured from
image texture (cells are textured, bare plastic is flat), because the instance
masks undercount coverage twice over: cells Cellpose misses contribute nothing,
and the thin processes of the cells it does find get trimmed off. On the 10x
Austin-Fibroblasts set that gap is large — 15% from the masks against ~46% of
the field actually covered.

So the app reports two different things:

| Number | What it means |
|---|---|
| **Confluency** | % of the growth surface covered by cells (from image texture) |
| **Area captured by masks** | % covered by the instances Cellpose counted |

The gap between them is how much cell area Cellpose is missing — useful as a
quality check on the diameter you picked.

The texture threshold is **absolute**: a pixel counts as covered when the local
standard deviation over a 25 px window is at least 26 gray levels of the
normalized image. Bare surface and covered surface separate cleanly on that
scale — measured on the saved runs, bare sits at a local SD of ~7–17 and a
fibroblast monolayer at ~31–63.

> **This changed.** The threshold used to be Otsu's, computed on a min-max
> rescaled copy of the texture map. Otsu assumes the image contains both
> classes, but a confluent field has no bare surface, so it split the cell
> population itself and reported a fraction of a fully covered plate — a saved
> run of a confluent monolayer scored **32%**, and measures **99%** now. The
> min-max rescaling made it worse by pinning the scale to the single most
> extreme speck of debris in the frame. On a ground-truth series (a known
> fraction of real cell texture composited onto real bare-surface texture) the
> old rule was **non-monotone** — 57% on an empty field, 21–85% on a fully
> covered one depending only on where the sensitivity slider sat. The absolute
> threshold recovers true coverage to within **~2 percentage points** from 0%
> to 100%. Confluency values from runs before this change are not comparable
> with values after it; `stats.json` now records `confluency_method` so the two
> can be told apart.

**Confluency still depends on a threshold, so verify it.** The *Cell Coverage*
overlay paints in red exactly what was counted. **Confluency sensitivity**
scales the threshold (lower = more of the field counted); **1.0** is the
calibrated value and should be right on 10x phase contrast. It is expressed on
the normalized scale so it is insensitive to exposure, but it does depend on
magnification. Keep it **fixed** across any experiment whose confluency values
you intend to compare.

One case the method cannot resolve on its own: an **empty field**. Normalizing
stretches whatever contrast exists to fill 0–255, so with no cells to set the
scale, sensor noise gets amplified until bare plastic looks textured and
confluency reads near 100%. Nothing in a single frame distinguishes that from a
real signal, so the app warns when the raw contrast is under 10% of full scale
rather than silently adjusting the number. The margin is thin (the flattest
bare patch measured 8.6%, real fields 15–35%), so treat it as a prompt to look
at the overlay, not as a verdict.

Confluency is a property of the image, so it does not change with diameter and
is not swept.

### Quality flags

Every run returns `quality_flags` — machine-readable reasons not to trust the
result — rendered above the statistics and summarised in the status line. They
cost nothing: all of them come from numbers the worker already computed.

| code | fires when | severity |
|---|---|---|
| `masks_missed_cells` | mask coverage is under 30% of measured confluency (10% → error) | warn / error |
| `no_cells` | nothing segmented on a field that is not empty | error |
| `empty_field` | confluency under 2% | warn |
| `low_contrast` | raw contrast under 10% of full scale | warn |
| `clipped` | over 1% of pixels pinned at black or white | warn |

`masks_missed_cells` is the one that matters: it is what makes the confluent
monolayer failure announce itself instead of quietly returning 206 cells. Its
thresholds sit in a wide gap — a healthy 10x run measured a ratio of 0.38,
the confluent failure 0.005, ~75x apart.

`clipped` is **uncalibrated**: not one of the 25 saved runs clips a single
pixel, so its 1% threshold has never fired against real data. It is warn-only.

`confluency_warning` is still populated for older UIs; new ones prefer the
structured list.

### Speed

Segmentation dominates; everything else is noise. On a 2048x1536 field:

| | before | now |
|---|---|---|
| Single diameter | ~19 s | **~3.5 s** |
| 5-point sweep | ~95 s | **~11.5 s** |

Two changes got that:

- **Apple Silicon GPU.** Cellpose was falling back to CPU because the device
  check only looked for CUDA. It now uses Metal (`mps`) when CUDA is absent —
  ~4x faster locally, with 99.4% pixel agreement against CPU and cell counts
  within 1%. Set `CELLPOSE_DISABLE_MPS=1` to force CPU if you are reconciling
  local numbers against a production run.
- **The image panels no longer go through matplotlib.** They are images, not
  charts, and matplotlib was rendering a 2048x1536 field into a 400 px
  thumbnail for ~150–280 ms each. Writing them straight from the array is
  ~10x faster *and* sharper: panels now come back at up to 1024 px (sweep
  masks 640 px, since a dozen can travel in one response). The histogram and
  the sweep chart are still matplotlib, because those really are charts.

The photographic panels ship as JPEG and the masks as PNG, which keeps a
12-point sweep's response near 1 MB. Artifacts written to the volume stay
lossless PNG.

A sweep costs one segmentation per diameter, so it scales linearly — but
larger diameters are *cheaper*, because Cellpose downscales the image to bring
the given diameter to its training size. A 40–150 px sweep runs faster than a
25–47 px one.

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
