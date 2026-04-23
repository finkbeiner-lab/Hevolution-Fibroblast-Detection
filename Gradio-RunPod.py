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
"""

import base64
import io
import logging
import os
import time

import gradio as gr
import requests
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

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


def invoke_runpod(image, diameter, denoise, blur, cell_line):
    """Submit a job to the RunPod endpoint and poll for the result.

    Returns (normalized_image, mask_image, histogram_image, stats_markdown, status_text).
    """
    cfg_err = _config_error()
    if cfg_err:
        return None, None, None, cfg_err, cfg_err

    if image is None:
        msg = "Please upload an image first."
        return None, None, None, msg, msg

    try:
        payload = {
            "input": {
                "image_b64": _image_to_b64(image),
                "diameter": float(diameter) if diameter else None,
                "denoise": bool(denoise),
                "blur": bool(blur),
                "cell_line": cell_line if cell_line and cell_line != "(Not specified)" else None,
            }
        }

        logger.info("Submitting job to RunPod endpoint %s", RUNPOD_ENDPOINT_ID)
        submit = requests.post(
            f"{RUNPOD_BASE}/run", json=payload, headers=AUTH_HEADER, timeout=30
        )
        submit.raise_for_status()
        job = submit.json()
        job_id = job.get("id")
        if not job_id:
            err = f"RunPod did not return a job id. Response: {job}"
            return None, None, None, err, err
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
                if "error" in output:
                    err = f"Worker error: {output['error']}"
                    return None, None, None, err, err

                norm = _b64_to_image(output["normalized_b64"])
                mask = _b64_to_image(output["mask_b64"])
                hist = _b64_to_image(output["histogram_b64"])

                elapsed = int(time.time() - started)
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
                return norm, mask, hist, stats_md, f"Complete in {elapsed}s"

            if state in ("FAILED", "CANCELLED", "TIMED_OUT"):
                err = f"RunPod job {state}. Details: {data.get('error') or data}"
                return None, None, None, err, err

            # IN_QUEUE / IN_PROGRESS -> keep waiting
            time.sleep(POLL_SEC)

        err = f"Timed out after {TIMEOUT_SEC}s waiting for RunPod job {job_id}."
        return None, None, None, err, err

    except requests.HTTPError as e:
        err = f"HTTP error calling RunPod: {e.response.status_code} {e.response.text[:500]}"
        logger.exception("RunPod HTTP error")
        return None, None, None, err, err
    except Exception as e:
        logger.exception("Unexpected error")
        return None, None, None, f"Error: {e}", f"Error: {e}"


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
            diameter_slider = gr.Slider(
                minimum=5, maximum=100, step=1, value=30, label="Approx. Cell Diameter"
            )
            denoise_checkbox = gr.Checkbox(label="Apply Denoising")
            blur_checkbox = gr.Checkbox(label="Apply Gaussian Blur")
            run_btn = gr.Button("Run Detection", variant="primary")
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
            output2 = gr.Image(label="Segmentation Mask", interactive=False, height=300)
            output3 = gr.Image(label="Intensity Histogram", interactive=False)

    run_btn.click(
        fn=invoke_runpod,
        inputs=[image_input, diameter_slider, denoise_checkbox, blur_checkbox, cell_line_dropdown],
        outputs=[output1, output2, output3, stats_output, status_output],
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
