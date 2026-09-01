"""RunPod Serverless worker for fibroblast segmentation.

Contract
--------
Input JSON (job["input"]):
    image_b64 : str   (required) image bytes, base64-encoded. Any format PIL
                      can read - JPEG, PNG, TIFF (8/16/32-bit, multi-page),
                      BMP, WebP - at any bit depth. A
                      "data:image/...;base64,..." prefix is accepted.
    diameter  : float (optional) approx. cell diameter (px). null => auto.
    diameters : list  (optional) run a SWEEP over these diameters instead of a
                      single one, e.g. [15, 25, 35, 45]. Max 12 values per job.
                      When present, `diameter` is ignored and the response
                      carries `sweep` / `sweep_plot_b64` instead of the single
                      `cell_count` / `confluency` / `mask_b64` fields.
    denoise   : bool  (optional, default false)
    blur      : bool  (optional, default false)
    confluency_sensitivity : float (optional, default 1.0) scales the local-SD
                      threshold for the confluency foreground mask. Lower =
                      more of the field counted as covered. See
                      _foreground_mask(); 1.0 is the calibrated value.
    cell_line : str   (optional) GESTALT / Coriell cell line ID (e.g. "AG08498").
                      Persisted into stats.json so downstream analysis can
                      join image -> cell_line -> donor age for model training.

Output JSON:
    cell_count      : int
    confluency      : float   (percent of the field covered by cells, measured
                               from a texture-based foreground mask - NOT from
                               the Cellpose instance masks; see below)
    mask_coverage   : float   (percent of the field covered by the counted
                               instances; <= confluency, and the gap is how
                               much cell area Cellpose missed)
    min_intensity   : int
    max_intensity   : int
    cell_line       : str|null  (echoed back for convenience)
    normalized_b64  : str     PNG base64
    mask_b64        : str     PNG base64
    histogram_b64   : str     PNG base64
    confluency_overlay_b64 : str  PNG base64 (foreground mask over the image,
                               so the confluency number can be eyeballed)
    persist_path    : str     (only if a Network Volume is attached)

Why confluency is not derived from the instance masks
-----------------------------------------------------
Confluency asks "how much of the growth surface is covered by cells". The
Cellpose masks answer a different question - "which pixels belong to a cell I
could individually resolve" - and they undercount coverage twice over: cells
that are missed entirely contribute nothing, and the thin processes of the
cells that ARE found get trimmed off the mask. On 10x phase-contrast
fibroblasts that gap is large (measured: 15% from masks vs ~39% of the field
actually covered). Coverage is therefore measured independently, from image
texture. Cell COUNT still comes from Cellpose, which is the right tool for it.

Sweep output JSON (when `diameters` was supplied):
    sweep           : list of {diameter, cell_count, mask_coverage, mask_b64}
    sweep_plot_b64  : str     PNG base64 (count + mask coverage vs diameter)
    confluency      : float   one value for the whole image - it does not
                              depend on the diameter, so it is not swept
    normalized_b64  : str     PNG base64 (shared by every diameter)
    histogram_b64   : str     PNG base64 (shared by every diameter)
    min_intensity   : int
    max_intensity   : int
    cell_line       : str|null
On failure:
    { "error": str, "trace": str }

Persistent storage
------------------
If a RunPod Network Volume is attached to the endpoint it is mounted at
/runpod-volume. When present, every job writes a copy of its input and
outputs to:

    /runpod-volume/fibroblast/<job_id>/
        input.png
        normalized.png
        mask.png            (single-diameter jobs)
        mask_d<diameter>.png + sweep_plot.png   (sweep jobs)
        histogram.png
        stats.json

The response gets an extra `persist_path` field pointing at that directory.
If no volume is attached, persistence is silently skipped and the worker
still returns the same base64 payload to the caller.

The mount path and subdirectory can be overridden with the PERSIST_ROOT
and PERSIST_SUBDIR environment variables (useful for local testing).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

os.environ.setdefault("MPLBACKEND", "Agg")

import base64
import io
import traceback

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

# Extra kwargs for models.Cellpose(). The RunPod path (CUDA, or CPU with no
# accelerator) passes nothing beyond gpu=, exactly as before; only Apple
# Silicon needs an explicit device. Set CELLPOSE_DISABLE_MPS=1 to force CPU -
# MPS kernels are not bit-identical to CPU (measured: 99.4% pixel agreement,
# cell counts within 1%), which is fine for exploration but worth turning off
# if you are reconciling local numbers against a production run.
_DEVICE_KWARGS: dict = {}
try:
    import torch

    _GPU_AVAILABLE = torch.cuda.is_available()
    if not _GPU_AVAILABLE and not os.environ.get("CELLPOSE_DISABLE_MPS"):
        _mps = getattr(torch.backends, "mps", None)
        if _mps is not None and _mps.is_available():
            _GPU_AVAILABLE = True
            _DEVICE_KWARGS["device"] = torch.device("mps")
except Exception:
    _GPU_AVAILABLE = False

from cellpose import models
import runpod

# ----------------- Persistent storage (RunPod Network Volume) -----------------
#
# RunPod Serverless mounts an attached Network Volume at /runpod-volume.
# If no volume is attached, that path does not exist and persistence is
# silently skipped. Override the mount path with PERSIST_ROOT for local
# testing (e.g. PERSIST_ROOT=/tmp/fibroblast-persist).

# A sweep runs one full segmentation per diameter, so cost scales linearly
# with the number of points. Cap it so a slider mistake can't launch 200
# GPU-seconds of work.
MAX_SWEEP_POINTS = 12

# Local standard deviation, in gray levels of the percentile-normalized image,
# above which a pixel counts as covered by cells. Bare plastic and covered
# surface are cleanly separated on this scale: measured on the saved runs,
# bare surface sits at a local SD of ~7-17 and a fibroblast monolayer at
# ~31-63, so anything in the low-to-mid 20s separates them.
#
# Calibrated against a ground-truth series built by compositing a known
# fraction of real cell texture onto real bare-surface texture: 26 recovers
# the true coverage to within ~2 percentage points from 0% to 100%.
#
# This is a calibration constant, not a universal one. It is expressed on the
# normalized 0-255 scale, so it is insensitive to exposure, but it does depend
# on magnification (via `win`). Check the overlay on your own imaging setup,
# and keep it FIXED across any experiment whose confluency values you compare.
CONFLUENCY_TEXTURE_THRESHOLD = 26.0

# _normalize() stretches p1..p99 to fill 0-255, which is what makes the
# threshold above exposure-independent. The cost is that an EMPTY field, which
# has no real contrast to stretch, has its sensor noise amplified until bare
# plastic looks textured - and then confluency reads high. Nothing in a single
# frame distinguishes that from a genuine signal, so warn instead of guessing.
# Measured on the saved runs: the flattest bare patch spans 8.6% of the raw
# full scale, while fields containing cells span 15-35%. The margin either
# side of this line is thin, and it rests on a single bare sample, so it only
# ever produces a warning - never a different number.
LOW_CONTRAST_FRACTION = 0.10

# `confluency_sensitivity` scales that threshold. Lower counts more of the
# field as covered. 1.0 is the calibrated value.
DEFAULT_CONFLUENCY_SENSITIVITY = 1.0

PERSIST_ROOT = os.environ.get("PERSIST_ROOT", "/runpod-volume")
PERSIST_SUBDIR = os.environ.get("PERSIST_SUBDIR", "fibroblast")
PERSIST_ENABLED = os.path.isdir(PERSIST_ROOT) and os.access(PERSIST_ROOT, os.W_OK)

if PERSIST_ENABLED:
    try:
        os.makedirs(os.path.join(PERSIST_ROOT, PERSIST_SUBDIR), exist_ok=True)
        print(f"[startup] Persistence ENABLED at {PERSIST_ROOT}/{PERSIST_SUBDIR}")
    except OSError as _e:
        PERSIST_ENABLED = False
        print(f"[startup] Persistence DISABLED (cannot write to {PERSIST_ROOT}): {_e}")
else:
    print(
        f"[startup] Persistence DISABLED ({PERSIST_ROOT} not mounted). "
        f"Attach a Network Volume to the endpoint to enable per-job storage."
    )


# ----------------- Warm start: load the model once -----------------

_DEVICE_NAME = str(_DEVICE_KWARGS.get("device", "cuda" if _GPU_AVAILABLE else "cpu"))
print(f"[startup] Accelerator: {_DEVICE_NAME}")
MODEL = models.Cellpose(gpu=_GPU_AVAILABLE, model_type="cyto3", **_DEVICE_KWARGS)
print("[startup] Cellpose 'cyto3' loaded")


# ----------------- Helpers -----------------

def _b64_to_pil(b64: str) -> Image.Image:
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    raw = base64.b64decode(b64)
    img = Image.open(io.BytesIO(raw))
    # Multi-page TIFF (z-stack / time series): segment the first frame.
    if getattr(img, "n_frames", 1) > 1:
        print(f"[input] Multi-frame image ({img.n_frames} frames); using the first.")
        img.seek(0)
    return img


def _to_gray(img: Image.Image) -> np.ndarray:
    """Single-channel array from any PIL image, at its original bit depth.

    Bit depth is preserved here on purpose: _normalize() percentile-stretches
    to 8-bit later, and doing that from the true 16-bit values keeps far more
    contrast than letting PIL truncate to 8-bit first.
    """
    # Palette images decode to palette indices, which are not intensities.
    if img.mode in ("P", "PA"):
        img = img.convert("RGBA" if img.mode == "PA" else "RGB")

    arr = np.array(img)
    if arr.ndim == 2:
        return arr
    if arr.ndim == 3:
        if arr.shape[2] >= 3:
            rgb = arr[:, :, :3]
            # cvtColor needs uint8/uint16/float32; normalise the dtype first.
            if rgb.dtype not in (np.uint8, np.uint16, np.float32):
                rgb = rgb.astype(np.float32)
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        return arr[:, :, 0]  # LA, or any single-channel-plus-alpha layout
    raise ValueError(f"Unsupported image with shape {arr.shape}")


def _pil_to_b64(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _photo_b64(img: Image.Image) -> str:
    """JPEG for the photographic panels, which is what they are.

    The normalized field and the coverage overlay are grainy phase contrast;
    PNG stores that grain losslessly at ~700 KB and ~1.2 MB, and base64 adds
    a third on top. JPEG carries the same visual information at a tenth the
    size, which matters because every panel travels in the job response and
    a sweep can carry a dozen of them. Masks stay PNG - flat label colors
    compress well losslessly, and JPEG would blur instance boundaries.
    Artifacts persisted to the volume stay lossless PNG regardless.
    """
    return _pil_to_b64(img, fmt="JPEG")


def _fig_to_pil(fig) -> Image.Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _denoise(img: np.ndarray, h: int = 10) -> np.ndarray:
    img = np.clip(img, 0, 255).astype(np.uint8)
    if img.ndim == 2:
        return cv2.fastNlMeansDenoising(img, h=h)
    if img.ndim == 3 and img.shape[2] == 3:
        return cv2.fastNlMeansDenoisingColored(img, None, h, h, 7, 21)
    return img


def _normalize(img: np.ndarray, pct: tuple | None = None) -> np.ndarray:
    """Percentile-stretch to 8 bits. `pct` reuses an existing (p1, p99) pass;
    on a 3 MP image that percentile costs ~25 ms and two callers need it."""
    p1, p99 = np.percentile(img, (1, 99)) if pct is None else pct
    img = np.clip((img - p1) / (p99 - p1 + 1e-8), 0, 1)
    return (img * 255).astype(np.uint8)


def _foreground_mask(
    gray: np.ndarray,
    sensitivity: float = DEFAULT_CONFLUENCY_SENSITIVITY,
    win: int = 25,
    close_px: int = 21,
    open_px: int = 9,
) -> np.ndarray:
    """Boolean mask of the growth surface that is covered by cells.

    Cells carry texture (edges, halos, internal structure); bare plastic is
    flat. So threshold the LOCAL STANDARD DEVIATION rather than raw intensity,
    which makes this robust to the uneven illumination typical of phase
    contrast - a plain intensity threshold tracks the illumination gradient
    instead of the cells.

    The threshold is ABSOLUTE, on the normalized image's own gray scale. It
    used to be Otsu's threshold on a min-max rescaled copy of the SD map, and
    that was wrong in two compounding ways:

      * Otsu assumes the image contains both classes. A confluent field has no
        bare surface, so Otsu split the cell population itself - smooth cell
        bodies below, edges and halos above - and reported a fraction of a
        fully covered plate. On a saved run of a confluent monolayer it gave
        32%; the same image measures 99% here.
      * min-max rescaling threw away the absolute scale that carries the
        signal, and pinned it to the single most extreme speck of debris in
        the frame instead.

    Together those made the answer track the sensitivity slider rather than
    the plate: on a ground-truth series the old rule was non-monotone, scoring
    an empty field at 57% and a fully covered one at 21-85% depending only on
    the slider. Absolute thresholding recovers true coverage to within ~2
    percentage points across the same series.

    Morphological close then open joins texture within a cell and drops
    isolated specks. Deliberately NO hole filling: when the foreground touches
    the image border - normal at moderate confluency - a flood fill leaks and
    reports ~100% coverage. Measured on a real plate: 45% before filling,
    98% after.
    """
    g = gray.astype(np.float32)
    mu = cv2.blur(g, (win, win))
    var = cv2.blur(g * g, (win, win)) - mu * mu
    sd = np.sqrt(np.maximum(var, 0))

    thr = CONFLUENCY_TEXTURE_THRESHOLD * float(sensitivity)
    binary = ((sd >= thr).astype(np.uint8)) * 255

    if close_px:
        binary = cv2.morphologyEx(
            binary, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_px, close_px)),
        )
    if open_px:
        binary = cv2.morphologyEx(
            binary, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_px, open_px)),
        )
    return binary > 0


def _raw_contrast(gray: np.ndarray, pct: tuple | None = None) -> float:
    """p1..p99 spread of the ORIGINAL pixels, as a fraction of full scale."""
    if np.issubdtype(gray.dtype, np.integer):
        full = float(np.iinfo(gray.dtype).max)
    else:
        full = float(max(np.max(gray), 1.0))
    p1, p99 = np.percentile(gray, (1, 99)) if pct is None else pct
    return float(p99 - p1) / max(full, 1e-9)


def _coverage_percent(mask: np.ndarray) -> float:
    return float(100.0 * np.count_nonzero(mask) / mask.size)


def _persist_job_artifacts(
    job_id: str,
    input_pil: Image.Image,
    images: dict,
    stats: dict,
    params: dict,
) -> str | None:
    """Write this job's artifacts to the network volume. Returns the
    directory path on success, or None if persistence is disabled/failed.

    `images` maps output filename -> PIL image, so single-diameter jobs and
    sweeps (one mask per diameter, plus the sweep plot) share this code.
    """
    if not PERSIST_ENABLED:
        return None
    try:
        out_dir = os.path.join(PERSIST_ROOT, PERSIST_SUBDIR, job_id)
        os.makedirs(out_dir, exist_ok=True)

        # Save the original upload (convert to RGB so mode is predictable).
        if input_pil.mode not in ("RGB", "L"):
            input_pil = input_pil.convert("RGB")
        input_pil.save(os.path.join(out_dir, "input.png"))

        for filename, img in images.items():
            img.save(os.path.join(out_dir, filename))

        meta = {
            "job_id": job_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "params": params,
            "stats": stats,
        }
        with open(os.path.join(out_dir, "stats.json"), "w") as f:
            json.dump(meta, f, indent=2)

        return out_dir
    except Exception as e:
        print(f"[persist] Failed to write artifacts for job {job_id}: {e}")
        return None


# The image panels used to go through matplotlib, which rendered a 2048x1536
# field into a 4x4 inch figure - a 400 px thumbnail - and cost ~150-280 ms
# each. Writing them straight from the array is both ~10x faster and sharper,
# since the panels are images, not charts. The titles matplotlib drew are
# dropped: every one of them duplicated the Gradio label or gallery caption
# already shown next to the image.
#
# Sizes are capped because every panel is base64'd into the job response.
# Sweep masks get a tighter cap: there can be twelve of them in one response.
RENDER_MAX_PX = 1024
SWEEP_MASK_MAX_PX = 640


def _fit(arr: np.ndarray, max_px: int, nearest: bool = False) -> np.ndarray:
    """Downscale so the longest side is at most `max_px`. Never upscales.

    `nearest` for label images - interpolating instance ids would invent
    labels that are not in the segmentation.
    """
    h, w = arr.shape[:2]
    longest = max(h, w)
    if longest <= max_px:
        return arr
    f = max_px / longest
    return cv2.resize(
        arr, (max(1, round(w * f)), max(1, round(h * f))),
        interpolation=cv2.INTER_NEAREST if nearest else cv2.INTER_AREA,
    )


def _render_norm(norm_gray: np.ndarray) -> Image.Image:
    return Image.fromarray(_fit(norm_gray, RENDER_MAX_PX))


def _render_mask(masks: np.ndarray, max_px: int = RENDER_MAX_PX) -> Image.Image:
    """Instance labels in distinct colors, black background.

    A fixed-seed random LUT rather than a continuous colormap: neighbouring
    ids get unrelated colors, so touching cells stay visually separable.
    """
    small = _fit(masks, max_px, nearest=True)
    lut = np.random.default_rng(0).integers(
        60, 256, size=(int(masks.max()) + 1, 3), dtype=np.uint8
    )
    lut[0] = 0
    return Image.fromarray(lut[small])


def _render_confluency_overlay(norm_gray: np.ndarray, fg: np.ndarray,
                               confluency: float) -> Image.Image:
    """The foreground mask painted over the image.

    Confluency depends on a threshold, so the number is only trustworthy if
    you can see what it counted. This is that check.
    """
    rgb = cv2.cvtColor(norm_gray, cv2.COLOR_GRAY2RGB)
    rgb[fg] = (0.55 * rgb[fg] + 0.45 * np.array([255, 0, 0])).astype(np.uint8)
    return Image.fromarray(_fit(rgb, RENDER_MAX_PX))


def _render_hist(norm_gray: np.ndarray) -> Image.Image:
    # ax.hist() would re-bin every pixel in Python; the image is uint8, so its
    # histogram is a bincount. Same 256 bars, a fraction of the time.
    counts = np.bincount(norm_gray.ravel(), minlength=256)
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(np.arange(256), counts, width=1.0, color="gray", edgecolor="black",
           linewidth=0.3)
    ax.set_title("Intensity Histogram")
    ax.set_xlabel("Pixel Intensity")
    ax.set_ylabel("Frequency")
    return _fig_to_pil(fig)


def _render_visuals(norm_gray: np.ndarray, masks: np.ndarray):
    return _render_norm(norm_gray), _render_mask(masks), _render_hist(norm_gray)


def _render_sweep_plot(sweep: list, confluency: float | None = None) -> Image.Image:
    """Cell count and mask coverage against diameter.

    Confluency is a property of the IMAGE, not of the diameter, so it is drawn
    once as a reference line rather than swept. The gap between the coverage
    curve and that line is the cell area Cellpose failed to capture at each
    diameter - which is the thing worth reading here.

    Two stacked panels sharing the x-axis rather than one chart with two
    y-scales: the measures have different units and ranges, and a dual axis
    lets the reader infer crossings that are an artefact of the scaling.
    """
    d = [r["diameter"] for r in sweep]
    series = (
        ([r["cell_count"] for r in sweep], "#2a78d6", "Cells detected", "cells"),
        ([r["mask_coverage"] for r in sweep], "#eb6834",
         "Area captured by masks", "% of field"),
    )

    fig, axes = plt.subplots(2, 1, figsize=(6.5, 5.4), sharex=True)
    for ax, (ys, color, title, ylab) in zip(axes, series):
        ax.plot(d, ys, color=color, linewidth=2, marker="o", markersize=6,
                markerfacecolor=color, markeredgecolor="white", markeredgewidth=1.2)
        ax.set_title(title, loc="left", fontsize=11, color="#0b0b0b")
        ax.set_ylabel(ylab, fontsize=9, color="#52514e")
        ax.grid(True, axis="y", color="#e6e5e1", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.margins(y=0.20)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#c9c8c3")
        ax.spines["bottom"].set_color("#c9c8c3")
        ax.tick_params(colors="#52514e", labelsize=9)

    # One direct label, not a number on every point: the diameter that found
    # the most cells is the value the reader is scanning for.
    counts = [r["cell_count"] for r in sweep]
    peak = int(np.argmax(counts))
    # Keep the label inside the axes when the peak is at either end.
    ha = "center"
    if peak == 0:
        ha = "left"
    elif peak == len(d) - 1:
        ha = "right"
    axes[0].annotate(
        f"{counts[peak]} cells @ d={d[peak]:g}",
        xy=(d[peak], counts[peak]), xytext=(0, 10), textcoords="offset points",
        ha=ha, fontsize=9, color="#0b0b0b",
    )

    if confluency is not None:
        axes[1].axhline(confluency, color="#52514e", linewidth=1.2,
                        linestyle="--", zorder=1)
        axes[1].annotate(
            f"measured cell coverage {confluency:.1f}%",
            xy=(d[0], confluency), xytext=(0, 5), textcoords="offset points",
            ha="left", fontsize=8.5, color="#52514e",
        )
        axes[1].set_ylim(top=max(max(series[1][0]), confluency) * 1.25)

    axes[1].set_xlabel("Approx. cell diameter (px)", fontsize=10, color="#52514e")
    axes[1].set_xticks(d)
    fig.tight_layout()
    return _fig_to_pil(fig)


# ----------------- Handler -----------------

def handler(job):
    try:
        job_input = job.get("input") or {}

        image_b64 = job_input.get("image_b64")
        if not image_b64:
            return {"error": "Missing required field 'image_b64' in input."}

        diameter = job_input.get("diameter")
        if diameter is not None:
            try:
                diameter = float(diameter)
            except (TypeError, ValueError):
                return {"error": f"Invalid 'diameter' value: {diameter!r}"}

        diameters = job_input.get("diameters")
        if diameters is not None:
            if not isinstance(diameters, (list, tuple)) or not diameters:
                return {"error": "'diameters' must be a non-empty list of numbers."}
            if len(diameters) > MAX_SWEEP_POINTS:
                return {
                    "error": f"'diameters' accepts at most {MAX_SWEEP_POINTS} "
                             f"values per job (got {len(diameters)}); each one "
                             f"costs a full segmentation."
                }
            try:
                diameters = [float(d) for d in diameters]
            except (TypeError, ValueError):
                return {"error": f"Invalid value in 'diameters': {diameters!r}"}
            if any(d <= 0 for d in diameters):
                return {"error": "Every value in 'diameters' must be greater than 0."}

        sensitivity = job_input.get(
            "confluency_sensitivity", DEFAULT_CONFLUENCY_SENSITIVITY
        )
        try:
            sensitivity = float(sensitivity)
        except (TypeError, ValueError):
            return {"error": f"Invalid 'confluency_sensitivity': {sensitivity!r}"}
        if not 0.1 <= sensitivity <= 2.0:
            return {"error": "'confluency_sensitivity' must be between 0.1 and 2.0."}

        denoise = bool(job_input.get("denoise", False))
        blur = bool(job_input.get("blur", False))
        cell_line = job_input.get("cell_line")
        if cell_line is not None:
            cell_line = str(cell_line).strip() or None

        pil = _b64_to_pil(image_b64)
        gray = _to_gray(pil)

        # Normalise BEFORE denoise/blur. _denoise() clips to 0-255 for
        # cv2.fastNlMeansDenoising, so running it on 16-bit data first would
        # flatten everything above 255 to white and destroy the image.
        # Percentile-stretching to 8-bit up front makes the optional filters
        # safe at any input bit depth.
        raw_pct = tuple(np.percentile(gray, (1, 99)))
        norm_gray = _normalize(gray, pct=raw_pct)

        if denoise:
            norm_gray = _denoise(norm_gray)
        if blur:
            norm_gray = cv2.GaussianBlur(norm_gray, (5, 5), sigmaX=1.0)

        min_intensity = int(norm_gray.min())
        max_intensity = int(norm_gray.max())

        # The normalized view and the histogram depend only on the image, so
        # they are rendered once and shared across every diameter in a sweep.
        # Coverage is measured from the image, independently of Cellpose, and
        # does not depend on the diameter - so it is computed once.
        foreground = _foreground_mask(norm_gray, sensitivity=sensitivity)
        confluency = _coverage_percent(foreground)

        contrast = _raw_contrast(gray, pct=raw_pct)
        confluency_warning = None
        if contrast < LOW_CONTRAST_FRACTION:
            confluency_warning = (
                f"Low image contrast ({contrast * 100:.1f}% of full scale). "
                f"Normalization amplifies noise in a nearly empty field, so "
                f"confluency can read high on bare surface. Check the overlay."
            )

        norm_img = _render_norm(norm_gray)
        hist_img = _render_hist(norm_gray)
        overlay_img = _render_confluency_overlay(norm_gray, foreground, confluency)

        # RunPod sets job["id"]; fall back to a timestamp in local runs.
        job_id = job.get("id") or datetime.now(timezone.utc).strftime(
            "local-%Y%m%dT%H%M%S%f"
        )
        params = {
            "diameter": diameter,
            "diameters": diameters,
            "denoise": denoise,
            "blur": blur,
            "cell_line": cell_line,
            "confluency_sensitivity": sensitivity,
            # Recorded so runs measured with the old Otsu rule are never
            # silently compared against these.
            "confluency_method": (
                f"local-SD >= {CONFLUENCY_TEXTURE_THRESHOLD * sensitivity:.1f} "
                f"gray levels (absolute, v2)"
            ),
            "raw_contrast": contrast,
        }
        images = {
            "normalized.png": norm_img,
            "histogram.png": hist_img,
            "confluency_overlay.png": overlay_img,
        }

        if diameters:
            sweep = []
            for d in diameters:
                masks, _flows, _styles, _diams = MODEL.eval(
                    norm_gray, diameter=d, channels=[0, 0]
                )
                labels = np.unique(masks)
                entry = {
                    "diameter": d,
                    "cell_count": int((labels != 0).sum()),
                    "mask_coverage": _coverage_percent(masks),
                }
                mask_img = _render_mask(masks, max_px=SWEEP_MASK_MAX_PX)
                images[f"mask_d{d:g}.png"] = mask_img
                entry["mask_b64"] = _pil_to_b64(mask_img)
                sweep.append(entry)

            plot_img = _render_sweep_plot(sweep, confluency=confluency)
            images["sweep_plot.png"] = plot_img

            stats = {
                "confluency": confluency,
                "confluency_warning": confluency_warning,
                "sweep": [
                    {k: v for k, v in e.items() if k != "mask_b64"} for e in sweep
                ],
                "min_intensity": min_intensity,
                "max_intensity": max_intensity,
            }
            persist_path = _persist_job_artifacts(
                job_id=job_id, input_pil=pil, images=images,
                stats=stats, params=params,
            )
            response = {
                "sweep": sweep,
                "confluency": confluency,
                "confluency_warning": confluency_warning,
                "sweep_plot_b64": _pil_to_b64(plot_img),
                "normalized_b64": _photo_b64(norm_img),
                "histogram_b64": _pil_to_b64(hist_img),
                "confluency_overlay_b64": _photo_b64(overlay_img),
                "min_intensity": min_intensity,
                "max_intensity": max_intensity,
                "cell_line": cell_line,
            }
            if persist_path:
                response["persist_path"] = persist_path
            return response

        masks, _flows, _styles, _diams = MODEL.eval(
            norm_gray, diameter=diameter, channels=[0, 0]
        )

        labels = np.unique(masks)
        mask_img = _render_mask(masks)
        images["mask.png"] = mask_img

        stats = {
            "cell_count": int((labels != 0).sum()),
            "confluency": confluency,
            "confluency_warning": confluency_warning,
            "mask_coverage": _coverage_percent(masks),
            "min_intensity": min_intensity,
            "max_intensity": max_intensity,
        }

        persist_path = _persist_job_artifacts(
            job_id=job_id, input_pil=pil, images=images,
            stats=stats, params=params,
        )

        response = {
            **stats,
            "cell_line": cell_line,
            "normalized_b64": _photo_b64(norm_img),
            "mask_b64": _pil_to_b64(mask_img),
            "histogram_b64": _pil_to_b64(hist_img),
            "confluency_overlay_b64": _photo_b64(overlay_img),
        }
        if persist_path:
            response["persist_path"] = persist_path
        return response

    except Exception as e:
        return {"error": str(e), "trace": traceback.format_exc()}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
