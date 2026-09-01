"""RunPod Serverless worker for fibroblast segmentation.

Contract
--------
Input JSON (job["input"]):
    image_b64 : str   (required) PNG/JPEG bytes, base64-encoded. A
                      "data:image/...;base64,..." prefix is accepted.
    diameter  : float (optional) approx. cell diameter (px). null => auto.
    diameters : list  (optional) run a SWEEP over these diameters instead of a
                      single one, e.g. [15, 25, 35, 45]. Max 12 values per job.
                      When present, `diameter` is ignored and the response
                      carries `sweep` / `sweep_plot_b64` instead of the single
                      `cell_count` / `confluency` / `mask_b64` fields.
    denoise   : bool  (optional, default false)
    blur      : bool  (optional, default false)
    cell_line : str   (optional) GESTALT / Coriell cell line ID (e.g. "AG08498").
                      Persisted into stats.json so downstream analysis can
                      join image -> cell_line -> donor age for model training.

Output JSON:
    cell_count      : int
    confluency      : float   (percent)
    min_intensity   : int
    max_intensity   : int
    cell_line       : str|null  (echoed back for convenience)
    normalized_b64  : str     PNG base64
    mask_b64        : str     PNG base64
    histogram_b64   : str     PNG base64
    persist_path    : str     (only if a Network Volume is attached)

Sweep output JSON (when `diameters` was supplied):
    sweep           : list of {diameter, cell_count, confluency, mask_b64}
    sweep_plot_b64  : str     PNG base64 (count + confluency vs diameter)
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

try:
    import torch

    _GPU_AVAILABLE = torch.cuda.is_available()
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

print(f"[startup] CUDA available: {_GPU_AVAILABLE}")
MODEL = models.Cellpose(gpu=_GPU_AVAILABLE, model_type="cyto3")
print("[startup] Cellpose 'cyto3' loaded")


# ----------------- Helpers -----------------

def _b64_to_pil(b64: str) -> Image.Image:
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    raw = base64.b64decode(b64)
    return Image.open(io.BytesIO(raw))


def _pil_to_b64(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("ascii")


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


def _normalize(img: np.ndarray) -> np.ndarray:
    p1, p99 = np.percentile(img, (1, 99))
    img = np.clip((img - p1) / (p99 - p1 + 1e-8), 0, 1)
    return (img * 255).astype(np.uint8)


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


def _render_norm(norm_gray: np.ndarray) -> Image.Image:
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.imshow(norm_gray, cmap="gray")
    ax.set_title("Normalized Image")
    ax.axis("off")
    return _fig_to_pil(fig)


def _render_mask(masks: np.ndarray, title: str = "Segmentation Mask") -> Image.Image:
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.imshow(masks, cmap="nipy_spectral")
    ax.set_title(title)
    ax.axis("off")
    return _fig_to_pil(fig)


def _render_hist(norm_gray: np.ndarray) -> Image.Image:
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.hist(norm_gray.ravel(), bins=256, range=(0, 255), color="gray", edgecolor="black")
    ax.set_title("Intensity Histogram")
    ax.set_xlabel("Pixel Intensity")
    ax.set_ylabel("Frequency")
    return _fig_to_pil(fig)


def _render_visuals(norm_gray: np.ndarray, masks: np.ndarray):
    return _render_norm(norm_gray), _render_mask(masks), _render_hist(norm_gray)


def _render_sweep_plot(sweep: list) -> Image.Image:
    """Cell count and confluency against diameter.

    Two stacked panels sharing the x-axis rather than one chart with two
    y-scales: the measures have different units and ranges, and a dual axis
    lets the reader infer crossings that are an artefact of the scaling.
    """
    d = [r["diameter"] for r in sweep]
    series = (
        ([r["cell_count"] for r in sweep], "#2a78d6", "Cells detected", "cells"),
        ([r["confluency"] for r in sweep], "#eb6834", "Confluency", "% of field"),
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

        denoise = bool(job_input.get("denoise", False))
        blur = bool(job_input.get("blur", False))
        cell_line = job_input.get("cell_line")
        if cell_line is not None:
            cell_line = str(cell_line).strip() or None

        pil = _b64_to_pil(image_b64)
        img = np.array(pil)

        if img.ndim == 3 and img.shape[2] == 4:
            img = img[:, :, :3]
        if img.ndim == 3 and img.shape[2] == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            gray = img.copy()

        if denoise:
            gray = _denoise(gray)
        if blur:
            gray = cv2.GaussianBlur(gray, (5, 5), sigmaX=1.0)

        norm_gray = _normalize(gray)

        min_intensity = int(norm_gray.min())
        max_intensity = int(norm_gray.max())

        # The normalized view and the histogram depend only on the image, so
        # they are rendered once and shared across every diameter in a sweep.
        norm_img = _render_norm(norm_gray)
        hist_img = _render_hist(norm_gray)

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
        }
        images = {"normalized.png": norm_img, "histogram.png": hist_img}

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
                    "confluency": float(100.0 * np.count_nonzero(masks) / masks.size),
                }
                mask_img = _render_mask(
                    masks, f"d = {d:g} px  |  {entry['cell_count']} cells"
                )
                images[f"mask_d{d:g}.png"] = mask_img
                entry["mask_b64"] = _pil_to_b64(mask_img)
                sweep.append(entry)

            plot_img = _render_sweep_plot(sweep)
            images["sweep_plot.png"] = plot_img

            stats = {
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
                "sweep_plot_b64": _pil_to_b64(plot_img),
                "normalized_b64": _pil_to_b64(norm_img),
                "histogram_b64": _pil_to_b64(hist_img),
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
            "confluency": float(100.0 * np.count_nonzero(masks) / masks.size),
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
            "normalized_b64": _pil_to_b64(norm_img),
            "mask_b64": _pil_to_b64(mask_img),
            "histogram_b64": _pil_to_b64(hist_img),
        }
        if persist_path:
            response["persist_path"] = persist_path
        return response

    except Exception as e:
        return {"error": str(e), "trace": traceback.format_exc()}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
