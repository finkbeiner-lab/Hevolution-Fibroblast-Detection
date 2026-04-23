"""RunPod Serverless worker for fibroblast segmentation.

Contract
--------
Input JSON (job["input"]):
    image_b64 : str   (required) PNG/JPEG bytes, base64-encoded. A
                      "data:image/...;base64,..." prefix is accepted.
    diameter  : float (optional) approx. cell diameter (px). null => auto.
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
        mask.png
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
    norm_img: Image.Image,
    mask_img: Image.Image,
    hist_img: Image.Image,
    stats: dict,
    params: dict,
) -> str | None:
    """Write this job's artifacts to the network volume. Returns the
    directory path on success, or None if persistence is disabled/failed."""
    if not PERSIST_ENABLED:
        return None
    try:
        out_dir = os.path.join(PERSIST_ROOT, PERSIST_SUBDIR, job_id)
        os.makedirs(out_dir, exist_ok=True)

        # Save the original upload (convert to RGB so mode is predictable).
        if input_pil.mode not in ("RGB", "L"):
            input_pil = input_pil.convert("RGB")
        input_pil.save(os.path.join(out_dir, "input.png"))

        norm_img.save(os.path.join(out_dir, "normalized.png"))
        mask_img.save(os.path.join(out_dir, "mask.png"))
        hist_img.save(os.path.join(out_dir, "histogram.png"))

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


def _render_visuals(norm_gray: np.ndarray, masks: np.ndarray):
    fig1, ax1 = plt.subplots(figsize=(4, 4))
    ax1.imshow(norm_gray, cmap="gray")
    ax1.set_title("Normalized Image")
    ax1.axis("off")
    norm_img = _fig_to_pil(fig1)

    fig2, ax2 = plt.subplots(figsize=(4, 4))
    ax2.imshow(masks, cmap="nipy_spectral")
    ax2.set_title("Segmentation Mask")
    ax2.axis("off")
    mask_img = _fig_to_pil(fig2)

    fig3, ax3 = plt.subplots(figsize=(4, 3))
    ax3.hist(norm_gray.ravel(), bins=256, range=(0, 255), color="gray", edgecolor="black")
    ax3.set_title("Intensity Histogram")
    ax3.set_xlabel("Pixel Intensity")
    ax3.set_ylabel("Frequency")
    hist_img = _fig_to_pil(fig3)

    return norm_img, mask_img, hist_img


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

        masks, _flows, _styles, _diams = MODEL.eval(
            norm_gray, diameter=diameter, channels=[0, 0]
        )

        labels = np.unique(masks)
        cell_count = int((labels != 0).sum())
        confluency = float(100.0 * np.count_nonzero(masks) / masks.size)
        min_intensity = int(norm_gray.min())
        max_intensity = int(norm_gray.max())

        norm_img, mask_img, hist_img = _render_visuals(norm_gray, masks)

        stats = {
            "cell_count": cell_count,
            "confluency": confluency,
            "min_intensity": min_intensity,
            "max_intensity": max_intensity,
        }

        # Optional per-job persistence on /runpod-volume.
        # RunPod sets job["id"]; fall back to a timestamp in local runs.
        job_id = job.get("id") or datetime.now(timezone.utc).strftime(
            "local-%Y%m%dT%H%M%S%f"
        )
        persist_path = _persist_job_artifacts(
            job_id=job_id,
            input_pil=pil,
            norm_img=norm_img,
            mask_img=mask_img,
            hist_img=hist_img,
            stats=stats,
            params={
                "diameter": diameter,
                "denoise": denoise,
                "blur": blur,
                "cell_line": cell_line,
            },
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
