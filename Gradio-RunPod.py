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

import gradio as gr
import requests
from PIL import Image

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


def _image_to_b64(image: Image.Image) -> str:
    """Encode for transport to RunPod. Try PNG first (lossless); fall back to
    high-quality JPEG and then to a resized JPEG if the image is too large
    for RunPod's 10 MiB body limit.
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    if buf.tell() <= _MAX_RAW_IMAGE_BYTES:
        return base64.b64encode(buf.getvalue()).decode("ascii")

    # Too big as PNG. Re-encode as JPEG at near-lossless quality.
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=95, optimize=True)
    if buf.tell() > _MAX_RAW_IMAGE_BYTES:
        # Still too big — downscale. Shrink pixel count proportionally to fit.
        scale = (_MAX_RAW_IMAGE_BYTES / buf.tell()) ** 0.5 * 0.95
        new_size = (max(1, int(image.size[0] * scale)), max(1, int(image.size[1] * scale)))
        image = image.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=92, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _b64_to_image(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64)))


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
    return (None, None, None, msg, msg, None, None, None)


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

    gallery = [
        (_b64_to_image(e["mask_b64"]), f"d = {e['diameter']:g} px | {e['cell_count']} cells")
        for e in sweep
    ]
    table = [
        [e["diameter"], e["cell_count"], round(e["confluency"], 2)] for e in sweep
    ]

    line_tag = output.get("cell_line") or (
        cell_line if cell_line and cell_line != "(Not specified)" else "—"
    )
    best = max(sweep, key=lambda e: e["cell_count"])
    stats_md = (
        "### Sweep\n\n"
        f"**Cell Line:** {line_tag}\n\n"
        f"**Diameters tried:** {len(sweep)} "
        f"({sweep[0]['diameter']:g}–{sweep[-1]['diameter']:g} px)\n\n"
        f"**Most cells:** {best['cell_count']} at d = {best['diameter']:g} px\n\n"
        f"**Min Intensity:** {output['min_intensity']}\n\n"
        f"**Max Intensity:** {output['max_intensity']}\n\n"
        f"**Processing Time:** {elapsed} s\n\n"
        "_Highest count is not automatically the right diameter — compare the "
        "masks against the cells you can see._"
    )
    status = f"Swept {len(sweep)} diameters in {elapsed}s"
    return norm, None, hist, stats_md, status, plot, gallery, table


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

    line_tag = output.get("cell_line") or (
        cell_line if cell_line and cell_line != "(Not specified)" else "—"
    )
    stats_md = (
        "### Statistics\n\n"
        f"**Cell Line:** {line_tag}\n\n"
        f"**Cell Count:** {output['cell_count']}\n\n"
        f"**Confluency:** {output['confluency']:.2f}%\n\n"
        f"**Min Intensity:** {output['min_intensity']}\n\n"
        f"**Max Intensity:** {output['max_intensity']}\n\n"
        f"**Processing Time:** {elapsed} s"
    )
    return (norm, mask, hist, stats_md, f"Complete in {elapsed}s",
            None, None, None)


def _invoke_local(job_input):
    """Run the RunPod worker in this process (LOCAL_INFERENCE=1).

    Imported lazily so the normal EC2 deployment never needs cellpose/torch.
    """
    from runpod_handler import handler

    job_id = datetime.now(timezone.utc).strftime("local-%Y%m%dT%H%M%S%f")
    return handler({"id": job_id, "input": job_input}) or {}


def invoke_runpod(image, mode, diameter, d_min, d_max, d_steps,
                  denoise, blur, cell_line):
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
            "image_b64": _image_to_b64(image),
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
            image_input = gr.Image(type="pil", label="Upload Image")
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
                    minimum=5, maximum=100, step=1, value=30,
                    label="Approx. Cell Diameter",
                )
            with gr.Group(visible=False) as sweep_controls:
                with gr.Row():
                    d_min_slider = gr.Slider(
                        minimum=5, maximum=100, step=1, value=15,
                        label="Smallest diameter",
                    )
                    d_max_slider = gr.Slider(
                        minimum=5, maximum=100, step=1, value=45,
                        label="Largest diameter",
                    )
                d_steps_slider = gr.Slider(
                    minimum=2, maximum=MAX_SWEEP_POINTS, step=1, value=5,
                    label="Number of diameters",
                    info=f"Each one is a full segmentation, so cost scales with this "
                         f"(max {MAX_SWEEP_POINTS}).",
                )
                sweep_preview = gr.Markdown()

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
                    headers=["Diameter (px)", "Cells", "Confluency (%)"],
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

    run_btn.click(
        fn=invoke_runpod,
        inputs=[image_input, mode_radio, diameter_slider,
                d_min_slider, d_max_slider, d_steps_slider,
                denoise_checkbox, blur_checkbox, cell_line_dropdown],
        outputs=[output1, output2, output3, stats_output, status_output,
                 sweep_plot_output, sweep_gallery, sweep_table],
    )

    demo.load(
        fn=_preview_sweep,
        inputs=[d_min_slider, d_max_slider, d_steps_slider],
        outputs=[sweep_preview],
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
