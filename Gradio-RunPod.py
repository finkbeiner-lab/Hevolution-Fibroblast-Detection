"""Gradio frontend for the fibroblast detection service.

This is the EC2-hosted UI. The heavy lifting (Cellpose segmentation) runs on
RunPod Serverless via `runpod_handler.py`. This file only talks to the RunPod
REST API — no AWS SDK, no torch, no cellpose.

Required environment variables:
    RUNPOD_API_KEY      : your RunPod API key (rpa_...)
    RUNPOD_ENDPOINT_ID  : the serverless endpoint id from the RunPod console

Optional:
    GRADIO_SERVER_NAME  : bind address (default 0.0.0.0 for EC2 hosting)
    GRADIO_SERVER_PORT  : default 7860
    RUNPOD_TIMEOUT_SEC  : max seconds to wait for a job (default 300)
    RUNPOD_POLL_SEC     : poll interval (default 3)

Local testing:
    LOCAL_INFERENCE=1   : skip RunPod entirely and call runpod_handler.handler()
                          in this process. Requires the worker dependencies
                          (cellpose, torch, opencv) to be installed locally and
                          needs no API key. The UI is identical either way.
"""

import base64
import io
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Local testing switch: run the worker in-process instead of on RunPod.
LOCAL_INFERENCE = os.getenv("LOCAL_INFERENCE", "").strip().lower() in ("1", "true", "yes")

RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "").strip()
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "").strip()
TIMEOUT_SEC = int(os.getenv("RUNPOD_TIMEOUT_SEC", "300"))
POLL_SEC = int(os.getenv("RUNPOD_POLL_SEC", "3"))

RUNPOD_BASE = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}" if RUNPOD_ENDPOINT_ID else ""
AUTH_HEADER = {"Authorization": f"Bearer {RUNPOD_API_KEY}"} if RUNPOD_API_KEY else {}

# GESTALT fibroblast cell lines (Coriell IDs). The selected value is passed as
# metadata with each job and written into stats.json on the Network Volume so
# downstream analysis (e.g. an age-prediction model) can join (image -> line ->
# donor age) without any re-labeling step. Edit to match what your lab uses.
GESTALT_CELL_LINES = [
    "(Not specified)",
    "TP0149 A",
    "TP0197 A",
    "TP0202 A",
    "TP0258 A",
    "TP0279 A",
    "TP0298 A",
    "TP0357 A",
    "TP0359 A",
    "TP0388 A",
    "TP0397 A",
    "TP0398 A",
    "Other",
]

SINGLE_MODE = "Single diameter"
SWEEP_MODE = "Diameter sweep"


# RunPod caps request bodies at 10 MiB. Base64 inflates by 4/3, plus we need
# headroom for the JSON wrapper and HTTP framing. Leave ~500 KiB of slack.
_MAX_RAW_IMAGE_BYTES = int((10 * 1024 * 1024 - 500_000) * 3 / 4)

# Modes PNG can store directly. Anything else has to be coerced first, but
# only on the oversized path - normally the original bytes are sent untouched.
_PNG_DIRECT_MODES = {
    "1", "L", "LA", "P", "PA", "RGB", "RGBA", "I;16", "I;16B", "I;16L",
}


def _open_any(path: str) -> Image.Image:
    """Open any format PIL can read.

    Multi-page TIFFs (z-stacks, time series) are common in microscopy; take
    the first frame rather than failing.
    """
    img = Image.open(path)
    if getattr(img, "n_frames", 1) > 1:
        logger.info("Multi-frame image (%d frames); using the first.", img.n_frames)
        img.seek(0)
    return img


def _to_png_safe(img: Image.Image) -> Image.Image:
    """Coerce a PIL image into a mode PNG can actually store."""
    if img.mode in _PNG_DIRECT_MODES:
        return img
    if img.mode in ("I", "F") or img.mode.startswith("I;32"):
        # 32-bit int / float TIFF. PNG tops out at 16 bits per channel, which
        # is already more range than the segmentation uses, so rescale rather
        # than convert("L") - that truncates and can black out the image.
        arr = np.asarray(img).astype("float64")
        lo, hi = float(arr.min()), float(arr.max())
        arr = (arr - lo) / (hi - lo) if hi > lo else np.zeros_like(arr)
        return Image.fromarray((arr * 65535).astype("uint16"))
    return img.convert("RGB")


def _encode_for_transport(path: str) -> str:
    """Base64-encode the uploaded file for the worker.

    Sends the ORIGINAL bytes whenever they fit. That preserves bit depth and
    format exactly - a 16-bit TIFF stays 16-bit - and avoids inflating a small
    JPEG into a multi-megabyte PNG. Only oversized images are decoded, and
    only then are they downscaled.
    """
    raw = Path(path).read_bytes()
    if len(raw) <= _MAX_RAW_IMAGE_BYTES:
        return base64.b64encode(raw).decode("ascii")

    img = _to_png_safe(_open_any(path))
    for scale in (1.0, 0.75, 0.5, 0.35, 0.25, 0.15):
        w, h = img.size
        candidate = (
            img if scale == 1.0
            else img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                            Image.LANCZOS)
        )
        buf = io.BytesIO()
        candidate.save(buf, format="PNG")
        if buf.tell() <= _MAX_RAW_IMAGE_BYTES:
            if scale != 1.0:
                logger.warning(
                    "Image downscaled to %.0f%% to fit the request limit; "
                    "pixel diameters scale with it.", scale * 100,
                )
            return base64.b64encode(buf.getvalue()).decode("ascii")

    raise ValueError(
        f"Image is too large to send even at 15% scale ({len(raw) / 1e6:.1f} MB). "
        "Crop or downsample it first."
    )


def _b64_to_image(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64)))


# ----------------- Upload preview -----------------
# Browsers cannot display TIFF, so an uploaded TIFF shows as an empty box even
# though the file is perfectly readable - which is why it appears in the
# Normalized Image and Cell Coverage results but not at the upload control.
# We therefore render our own 8-bit preview, and draw the diameter Cellpose
# will be given on top of it so it can be judged against the actual cells
# before paying for a segmentation.

MAX_PREVIEW_PX = 1200
GUIDE_COLOR = (255, 214, 0)

# Tried in order; the frontend has no matplotlib, so DejaVu is not guaranteed.
_FONT_CANDIDATES = (
    "DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _font(size: int):
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _label(draw, xy, text, font):
    """Draw text with a dark halo, falling back if the font lacks stroke."""
    try:
        draw.text(xy, text, fill=GUIDE_COLOR, font=font,
                  stroke_width=2, stroke_fill=(0, 0, 0))
    except (ValueError, TypeError, AttributeError):
        draw.text(xy, text, fill=GUIDE_COLOR, font=font)


def _gray_array(img: Image.Image) -> np.ndarray:
    """Single-channel array from any PIL image, at its original bit depth."""
    if img.mode in ("P", "PA"):
        img = img.convert("RGBA" if img.mode == "PA" else "RGB")
    arr = np.asarray(img)
    if arr.ndim == 2:
        return arr
    if arr.ndim == 3:
        if arr.shape[2] >= 3:
            return arr[:, :, :3].astype("float32").mean(axis=2)
        return arr[:, :, 0]
    raise ValueError(f"Unsupported image with shape {arr.shape}")


def _preview_base(path: str):
    """(RGB preview, scale) for an uploaded file.

    Percentile-stretched to 8 bits the same way the worker normalizes, so a
    16-bit TIFF looks like its "Normalized Image" result instead of the near
    black rectangle a plain 8-bit conversion produces. `scale` is how much the
    preview was resized by, so guides drawn on it stay true to the pixel
    diameters the worker will actually use.
    """
    arr = _gray_array(_open_any(path)).astype("float32")
    p1, p99 = np.percentile(arr, (1, 99))
    arr = np.clip((arr - p1) / (p99 - p1 + 1e-8), 0, 1)
    img = Image.fromarray((arr * 255).astype("uint8")).convert("RGB")

    scale = 1.0
    longest = max(img.size)
    if longest > MAX_PREVIEW_PX:
        scale = MAX_PREVIEW_PX / longest
        img = img.resize(
            (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
            Image.LANCZOS,
        )
    return img, scale


def _draw_guides(base: Image.Image, scale: float, diameters) -> Image.Image:
    """Draw each diameter as a true-size ring laid out across the image.

    Side by side rather than concentric: a 12-point sweep drawn about one
    centre is a solid dartboard that hides the cells underneath, which is
    exactly what the guide is meant to be compared against.
    """
    img = base.copy()
    draw = ImageDraw.Draw(img)
    line_w = max(2, round(min(img.size) / 400))
    font_px = max(13, round(min(img.size) / 45))
    font = _font(font_px)

    def text_w(text):
        try:
            return draw.textlength(text, font=font)
        except Exception:
            return len(text) * font_px * 0.6

    margin, gap = font_px, max(6, font_px // 2)
    avail = max(1.0, img.width - 2 * margin)

    # Each ring gets a slot at least as wide as its own label, so labels stay
    # apart when a sweep packs several small diameters together.
    slots = [(d, d * scale / 2, max(d * scale, text_w(f"{d:g} px")))
             for d in sorted(diameters)]

    rows, row, used = [], [], 0.0
    for slot in slots:
        need = slot[2] + (gap if row else 0)
        if row and used + need > avail:
            rows.append(row)
            row, used, need = [], 0.0, slot[2]
        row.append(slot)
        used += need
    if row:
        rows.append(row)

    label_h = font_px + 4
    heights = [max(2 * r for _, r, _ in r_slots) + label_h for r_slots in rows]
    y = (img.height - (sum(heights) + gap * (len(rows) - 1))) / 2

    for r_slots, height in zip(rows, heights):
        row_w = sum(w for _, _, w in r_slots) + gap * (len(r_slots) - 1)
        x = (img.width - row_w) / 2
        cy = y + label_h + (height - label_h) / 2
        for d, r, slot_w in r_slots:
            cx = x + slot_w / 2
            draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                         outline=GUIDE_COLOR, width=line_w)
            text = f"{d:g} px"
            _label(draw, (cx - text_w(text) / 2, cy - r - label_h), text, font)
            x += slot_w + gap
        y += height + gap
    return img


def _diameters_for(mode, diameter, d_min, d_max, d_steps):
    """The diameters a run with these settings would use."""
    if mode == SWEEP_MODE:
        return _sweep_diameters(d_min, d_max, d_steps)
    return [round(float(diameter))]


def _load_preview(path):
    """Decode the upload once; slider moves then only redraw the guides."""
    if not path:
        return None
    try:
        base, scale = _preview_base(path)
        return {"base": base, "scale": scale, "name": Path(path).name}
    except Exception as e:
        logger.exception("Could not render a preview for %s", path)
        return {"error": str(e)}


def _refresh_preview(state, mode, diameter, d_min, d_max, d_steps):
    diameters = _diameters_for(mode, diameter, d_min, d_max, d_steps)
    listed = ", ".join(f"{d:g}" for d in diameters)

    if not state:
        return None, f"Upload an image to size it against the {listed} px guide."
    if "error" in state:
        return None, f"Could not render a preview: {state['error']}"

    if mode == SWEEP_MODE:
        body = (f"Rings show the {len(diameters)} diameters this sweep would "
                f"try ({listed} px).")
    else:
        body = f"Ring shows the {listed} px diameter Cellpose would assume."
    note = ""
    if state["scale"] < 1.0:
        note = (f" Preview is at {state['scale'] * 100:.0f}% of full size; the "
                "rings are scaled with it.")

    caption = (f"**{state['name']}** — {body} Adjust until a ring matches a "
               f"typical cell, then run.{note}")
    return _draw_guides(state["base"], state["scale"], diameters), caption


def _config_error() -> str | None:
    if LOCAL_INFERENCE:
        return None
    missing = []
    if not RUNPOD_API_KEY:
        missing.append("RUNPOD_API_KEY")
    if not RUNPOD_ENDPOINT_ID:
        missing.append("RUNPOD_ENDPOINT_ID")
    if missing:
        return (
            "Missing environment variables: " + ", ".join(missing) + ".\n\n"
            "Set them on the EC2 host (e.g. in the gradio-app systemd unit):\n"
            "  RUNPOD_API_KEY=rpa_...\n"
            "  RUNPOD_ENDPOINT_ID=<endpoint-id-from-runpod-console>"
        )
    return None


# A sweep runs one segmentation per diameter, so keep the count modest.
MAX_SWEEP_POINTS = 12

def _sweep_diameters(dmin, dmax, steps):
    """Evenly spaced integer diameters from dmin..dmax inclusive.

    Deduplicated, so a narrow range with many steps quietly costs less rather
    than segmenting the same diameter twice.
    """
    dmin, dmax, steps = float(dmin), float(dmax), int(steps)
    if dmin > dmax:
        dmin, dmax = dmax, dmin
    if steps < 2:
        return [round(dmin)]
    gap = (dmax - dmin) / (steps - 1)
    return sorted({round(dmin + i * gap) for i in range(steps)})


def _error(msg):
    """Uniform error tuple across every output slot."""
    return (None, None, None, msg, msg, None, None, None, None)


def _render_sweep(output, cell_line, elapsed):
    """Render a diameter sweep: shared views, a mask gallery, and a table."""
    if "error" in output:
        return _error(f"Worker error: {output['error']}")

    sweep = output.get("sweep") or []
    if not sweep:
        return _error("Worker returned an empty sweep.")

    norm = _b64_to_image(output["normalized_b64"])
    hist = _b64_to_image(output["histogram_b64"])
    plot = _b64_to_image(output["sweep_plot_b64"])

    overlay = _b64_to_image(output["confluency_overlay_b64"])
    confluency = output["confluency"]

    gallery = [
        (_b64_to_image(e["mask_b64"]), f"d = {e['diameter']:g} px | {e['cell_count']} cells")
        for e in sweep
    ]
    table = [
        [e["diameter"], e["cell_count"], round(e["mask_coverage"], 2)] for e in sweep
    ]

    line_tag = output.get("cell_line") or (
        cell_line if cell_line and cell_line != "(Not specified)" else "—"
    )
    warning = output.get("confluency_warning")
    best = max(sweep, key=lambda e: e["cell_count"])
    closest = max(sweep, key=lambda e: e["mask_coverage"])
    stats_md = (
        "### Sweep\n\n"
        + (f"> ⚠️ {warning}\n\n" if warning else "")
        + f"**Cell Line:** {line_tag}\n\n"
        f"**Confluency (whole image):** {confluency:.2f}%\n\n"
        f"**Diameters tried:** {len(sweep)} "
        f"({sweep[0]['diameter']:g}–{sweep[-1]['diameter']:g} px)\n\n"
        f"**Most cells:** {best['cell_count']} at d = {best['diameter']:g} px\n\n"
        f"**Best area capture:** {closest['mask_coverage']:.1f}% of the field "
        f"at d = {closest['diameter']:g} px\n\n"
        f"**Min Intensity:** {output['min_intensity']}\n\n"
        f"**Max Intensity:** {output['max_intensity']}\n\n"
        f"**Processing Time:** {elapsed} s\n\n"
        "_Confluency is measured from the image, so it does not change with "
        "diameter. The table shows how much of that area each diameter's masks "
        "actually captured — the closer to the confluency figure, the less "
        "Cellpose is missing. Highest cell count is not automatically right; "
        "compare the masks against the cells you can see._"
    )
    status = f"Swept {len(sweep)} diameters in {elapsed}s"
    return norm, None, hist, stats_md, status, plot, gallery, table, overlay


def _render_output(output, cell_line, elapsed):
    """Turn a worker response dict into the five Gradio outputs.

    Shared by the RunPod path and the LOCAL_INFERENCE path so both render
    results identically.
    """
    if "error" in output:
        return _error(f"Worker error: {output['error']}")

    norm = _b64_to_image(output["normalized_b64"])
    mask = _b64_to_image(output["mask_b64"])
    hist = _b64_to_image(output["histogram_b64"])
    overlay = _b64_to_image(output["confluency_overlay_b64"])

    line_tag = output.get("cell_line") or (
        cell_line if cell_line and cell_line != "(Not specified)" else "—"
    )
    warning = output.get("confluency_warning")
    stats_md = (
        "### Statistics\n\n"
        + (f"> ⚠️ {warning}\n\n" if warning else "")
        + f"**Cell Line:** {line_tag}\n\n"
        f"**Cell Count:** {output['cell_count']}\n\n"
        f"**Confluency:** {output['confluency']:.2f}%\n\n"
        f"**Area captured by masks:** {output.get('mask_coverage', float('nan')):.2f}%\n\n"
        f"**Min Intensity:** {output['min_intensity']}\n\n"
        f"**Max Intensity:** {output['max_intensity']}\n\n"
        f"**Processing Time:** {elapsed} s"
    )
    return (norm, mask, hist, stats_md, f"Complete in {elapsed}s",
            None, None, None, overlay)


def _invoke_local(job_input):
    """Run the RunPod worker in this process (LOCAL_INFERENCE=1).

    Imported lazily so the normal EC2 deployment never needs cellpose/torch.
    """
    from runpod_handler import handler

    job_id = datetime.now(timezone.utc).strftime("local-%Y%m%dT%H%M%S%f")
    return handler({"id": job_id, "input": job_input}) or {}


def invoke_runpod(image, mode, diameter, d_min, d_max, d_steps,
                  sensitivity, denoise, blur, cell_line):
    """Submit a job to the RunPod endpoint and poll for the result.

    `mode` is either "Single diameter" or "Diameter sweep"; the sweep runs one
    segmentation per diameter and returns a comparison instead of one mask.
    """
    cfg_err = _config_error()
    if cfg_err:
        return _error(cfg_err)

    if image is None:
        return _error("Please upload an image first.")

    sweeping = mode == SWEEP_MODE

    try:
        job_input = {
            "image_b64": _encode_for_transport(image),
            "confluency_sensitivity": float(sensitivity),
            "denoise": bool(denoise),
            "blur": bool(blur),
            "cell_line": cell_line if cell_line and cell_line != "(Not specified)" else None,
        }

        if sweeping:
            diameters = _sweep_diameters(d_min, d_max, d_steps)
            if len(diameters) > MAX_SWEEP_POINTS:
                return _error(
                    f"That is {len(diameters)} diameters; the limit is "
                    f"{MAX_SWEEP_POINTS} per run because each one costs a full "
                    f"segmentation. Reduce the number of steps."
                )
            job_input["diameters"] = diameters
            logger.info("Sweeping diameters: %s", diameters)
        else:
            job_input["diameter"] = float(diameter) if diameter else None

        payload = {"input": job_input}
        render = _render_sweep if sweeping else _render_output

        if LOCAL_INFERENCE:
            logger.info("LOCAL_INFERENCE=1 - running the worker in-process")
            started = time.time()
            output = _invoke_local(job_input)
            return render(output, cell_line, int(time.time() - started))

        logger.info("Submitting job to RunPod endpoint %s", RUNPOD_ENDPOINT_ID)
        submit = requests.post(
            f"{RUNPOD_BASE}/run", json=payload, headers=AUTH_HEADER, timeout=30
        )
        submit.raise_for_status()
        job = submit.json()
        job_id = job.get("id")
        if not job_id:
            return _error(f"RunPod did not return a job id. Response: {job}")
        logger.info("Job %s submitted, polling for result", job_id)

        status_url = f"{RUNPOD_BASE}/status/{job_id}"
        started = time.time()
        while time.time() - started < TIMEOUT_SEC:
            r = requests.get(status_url, headers=AUTH_HEADER, timeout=30)
            r.raise_for_status()
            data = r.json()
            state = data.get("status")

            if state == "COMPLETED":
                output = data.get("output") or {}
                return render(output, cell_line, int(time.time() - started))

            if state in ("FAILED", "CANCELLED", "TIMED_OUT"):
                return _error(f"RunPod job {state}. Details: {data.get('error') or data}")

            # IN_QUEUE / IN_PROGRESS -> keep waiting
            time.sleep(POLL_SEC)

        return _error(f"Timed out after {TIMEOUT_SEC}s waiting for RunPod job {job_id}.")

    except requests.HTTPError as e:
        logger.exception("RunPod HTTP error")
        return _error(
            f"HTTP error calling RunPod: {e.response.status_code} {e.response.text[:500]}"
        )
    except Exception as e:
        logger.exception("Unexpected error")
        return _error(f"Error: {e}")


# ----------------- Gradio UI -----------------

with gr.Blocks(title="Fibroblast Detection") as demo:
    gr.Markdown("## Fibroblast Confluency Detection")
    gr.Markdown("Upload a microscopy image to run Cellpose segmentation on RunPod serverless.")

    with gr.Row():
        with gr.Column():
            # gr.File, not gr.Image, for two reasons. It hands the worker
            # the file exactly as uploaded - gr.Image's default converts to
            # RGB first, which silently destroys a 16-bit TIFF - and it does
            # not try to render the upload in the browser, which is what left
            # TIFFs showing as an empty box. The preview below is ours.
            # No file_types filter: the worker takes anything PIL can read.
            image_input = gr.File(
                type="filepath",
                file_count="single",
                label="Upload Image (JPEG, PNG, TIFF, BMP, WebP, ...)",
            )
            cell_line_dropdown = gr.Dropdown(
                choices=GESTALT_CELL_LINES,
                value="(Not specified)",
                label="GESTALT Cell Line",
                info="Selecting a line tags the result with donor metadata (for future age-prediction modeling).",
            )
            mode_radio = gr.Radio(
                choices=[SINGLE_MODE, SWEEP_MODE],
                value=SINGLE_MODE,
                label="Diameter mode",
                info="Sweep segments the image once per diameter and compares them.",
            )
            with gr.Group() as single_controls:
                diameter_slider = gr.Slider(
                    minimum=5, maximum=200, step=1, value=30,
                    label="Approx. Cell Diameter (px)",
                )
            with gr.Group(visible=False) as sweep_controls:
                with gr.Row():
                    d_min_slider = gr.Slider(
                        minimum=5, maximum=200, step=1, value=40,
                        label="Smallest diameter (px)",
                    )
                    d_max_slider = gr.Slider(
                        minimum=5, maximum=200, step=1, value=120,
                        label="Largest diameter (px)",
                    )
                d_steps_slider = gr.Slider(
                    minimum=2, maximum=MAX_SWEEP_POINTS, step=1, value=5,
                    label="Number of diameters",
                    info=f"Each one is a full segmentation, so cost scales with this "
                         f"(max {MAX_SWEEP_POINTS}).",
                )
                sweep_preview = gr.Markdown()

            # Sits with the diameter controls rather than with the upload so
            # the ring and the slider moving it are visible at the same time.
            preview_state = gr.State()
            preview_image = gr.Image(
                label="Upload preview with diameter guide",
                interactive=False,
            )
            preview_caption = gr.Markdown()

            sensitivity_slider = gr.Slider(
                minimum=0.3, maximum=1.5, step=0.05, value=1.0,
                label="Confluency sensitivity",
                info="Scales the texture threshold; 1.0 is the calibrated "
                     "value and should be right on 10x phase contrast. Lower "
                     "counts more of the field as covered. Check the Cell "
                     "Coverage overlay, then keep it fixed across an experiment.",
            )
            denoise_checkbox = gr.Checkbox(label="Apply Denoising")
            blur_checkbox = gr.Checkbox(label="Apply Gaussian Blur")
            run_btn = gr.Button("Run Detection", variant="primary")
            if LOCAL_INFERENCE:
                gr.Markdown("**Backend:** `local (in-process cellpose)`")
            else:
                endpoint_label = RUNPOD_ENDPOINT_ID or "(not configured)"
                gr.Markdown(f"**RunPod endpoint:** `{endpoint_label}`")

        with gr.Column():
            status_output = gr.Textbox(
                label="Status",
                value="Ready. Upload an image and click 'Run Detection'.",
                interactive=False,
                lines=2,
            )
            stats_output = gr.Markdown(label="Statistics")
            output1 = gr.Image(label="Normalized Image", interactive=False)
            overlay_output = gr.Image(
                label="Cell Coverage (red = counted as covered)", interactive=False
            )
            with gr.Group() as single_results:
                output2 = gr.Image(
                    label="Segmentation Mask", interactive=False, height=300
                )
            with gr.Group(visible=False) as sweep_results:
                sweep_plot_output = gr.Image(
                    label="Cell count and confluency vs diameter", interactive=False
                )
                sweep_gallery = gr.Gallery(
                    label="Mask per diameter", columns=3, height=340,
                    object_fit="contain",
                )
                sweep_table = gr.Dataframe(
                    headers=["Diameter (px)", "Cells", "Area captured (%)"],
                    datatype=["number", "number", "number"],
                    label="Sweep results",
                    interactive=False,
                    wrap=True,
                )
            output3 = gr.Image(label="Intensity Histogram", interactive=False)

    def _toggle_mode(mode):
        """Show the controls and result panels for the selected mode."""
        sweeping = mode == SWEEP_MODE
        show_single = gr.update(visible=not sweeping)
        show_sweep = gr.update(visible=sweeping)
        return show_single, show_sweep, show_single, show_sweep

    mode_radio.change(
        fn=_toggle_mode,
        inputs=[mode_radio],
        outputs=[single_controls, sweep_controls, single_results, sweep_results],
    )

    def _preview_sweep(d_min, d_max, steps):
        vals = _sweep_diameters(d_min, d_max, steps)
        return (
            f"Will segment **{len(vals)}** times at: "
            + ", ".join(f"{v:g}" for v in vals)
            + " px"
        )

    for control in (d_min_slider, d_max_slider, d_steps_slider):
        control.change(
            fn=_preview_sweep,
            inputs=[d_min_slider, d_max_slider, d_steps_slider],
            outputs=[sweep_preview],
        )

    _preview_inputs = [preview_state, mode_radio, diameter_slider,
                       d_min_slider, d_max_slider, d_steps_slider]
    _preview_outputs = [preview_image, preview_caption]

    # Decode on upload only; every slider move just redraws the cached image.
    image_input.change(
        fn=_load_preview, inputs=[image_input], outputs=[preview_state],
    ).then(
        fn=_refresh_preview, inputs=_preview_inputs, outputs=_preview_outputs,
    )

    for control in (mode_radio, diameter_slider,
                    d_min_slider, d_max_slider, d_steps_slider):
        control.change(
            fn=_refresh_preview, inputs=_preview_inputs, outputs=_preview_outputs,
        )

    run_btn.click(
        fn=invoke_runpod,
        inputs=[image_input, mode_radio, diameter_slider,
                d_min_slider, d_max_slider, d_steps_slider,
                sensitivity_slider, denoise_checkbox, blur_checkbox,
                cell_line_dropdown],
        outputs=[output1, output2, output3, stats_output, status_output,
                 sweep_plot_output, sweep_gallery, sweep_table, overlay_output],
    )

    demo.load(
        fn=_preview_sweep,
        inputs=[d_min_slider, d_max_slider, d_steps_slider],
        outputs=[sweep_preview],
    )
    demo.load(
        fn=_refresh_preview, inputs=_preview_inputs, outputs=_preview_outputs,
    )

    gr.Markdown(
        "<div style='text-align:center; color:#888; font-size:0.85em; "
        "margin-top:2em; padding-top:1em; border-top:1px solid #eee;'>"
        "Built by Vivek Gopal Ramaswamy — Gladstone Institutes"
        "</div>"
    )


if __name__ == "__main__":
    server_name = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
    server_port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    share = os.getenv("GRADIO_SHARE", "False").lower() == "true"
    demo.launch(server_name=server_name, server_port=server_port, share=share)
