"""Gradio frontend (runs on AWS) that delegates inference to a RunPod
Serverless endpoint.

Required environment variables
------------------------------
RUNPOD_API_KEY       : your RunPod API key (https://www.runpod.io/console/user/settings)
RUNPOD_ENDPOINT_ID   : the serverless endpoint id (e.g. "abc123xyz")

Optional
--------
RUNPOD_POLL_TIMEOUT  : seconds to wait for job completion (default 300)
RUNPOD_POLL_INTERVAL : seconds between status polls (default 2)
GRADIO_SERVER_NAME   : default "0.0.0.0"
GRADIO_SERVER_PORT   : default 7860
GRADIO_SHARE         : "true"/"false", default false
"""

from __future__ import annotations

import base64
import io
import os
import time

import gradio as gr
import requests
from PIL import Image

RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.environ.get("RUNPOD_ENDPOINT_ID")
POLL_TIMEOUT = float(os.environ.get("RUNPOD_POLL_TIMEOUT", "300"))
POLL_INTERVAL = float(os.environ.get("RUNPOD_POLL_INTERVAL", "2"))

RUNPOD_BASE = "https://api.runpod.ai/v2"


# ----------------- RunPod client -----------------

def _require_config():
    if not RUNPOD_API_KEY or not RUNPOD_ENDPOINT_ID:
        raise gr.Error(
            "Backend not configured: set RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID "
            "environment variables on the Gradio host."
        )


def _headers():
    return {
        "Authorization": f"Bearer {RUNPOD_API_KEY}",
        "Content-Type": "application/json",
    }


def _pil_to_b64(img: Image.Image) -> str:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _b64_to_pil(b64: str) -> Image.Image:
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def call_runpod(payload: dict) -> dict:
    """Submit a job to RunPod Serverless and poll until completion."""
    _require_config()

    submit_url = f"{RUNPOD_BASE}/{RUNPOD_ENDPOINT_ID}/run"
    status_url_tmpl = f"{RUNPOD_BASE}/{RUNPOD_ENDPOINT_ID}/status/{{}}"

    try:
        r = requests.post(submit_url, json=payload, headers=_headers(), timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        raise gr.Error(f"Failed to submit job to RunPod: {e}") from e

    job = r.json()
    job_id = job.get("id")
    if not job_id:
        raise gr.Error(f"RunPod did not return a job id. Response: {job}")

    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        try:
            sr = requests.get(status_url_tmpl.format(job_id), headers=_headers(), timeout=30)
            sr.raise_for_status()
        except requests.RequestException as e:
            raise gr.Error(f"Failed to poll RunPod job {job_id}: {e}") from e

        data = sr.json()
        status = data.get("status")

        if status == "COMPLETED":
            return data.get("output") or {}
        if status in ("FAILED", "CANCELLED", "TIMED_OUT"):
            raise gr.Error(
                f"RunPod job {job_id} ended with status {status}. "
                f"Details: {data.get('error') or data}"
            )
        time.sleep(POLL_INTERVAL)

    raise gr.Error(f"RunPod job {job_id} did not complete within {POLL_TIMEOUT:.0f}s.")


# ----------------- Gradio handler -----------------

def process_image(image, diameter=None, denoise=False, blur=False):
    if image is None:
        raise gr.Error("Please upload an image first.")

    payload = {
        "input": {
            "image_b64": _pil_to_b64(image),
            "diameter": float(diameter) if diameter is not None else None,
            "denoise": bool(denoise),
            "blur": bool(blur),
        }
    }

    output = call_runpod(payload)

    if not isinstance(output, dict):
        raise gr.Error(f"Unexpected response from RunPod: {output!r}")
    if "error" in output:
        raise gr.Error(f"Inference error: {output['error']}")

    required = ("normalized_b64", "mask_b64", "histogram_b64",
                "cell_count", "confluency", "min_intensity", "max_intensity")
    missing = [k for k in required if k not in output]
    if missing:
        raise gr.Error(f"Malformed response from RunPod, missing keys: {missing}")

    norm_img = _b64_to_pil(output["normalized_b64"])
    mask_img = _b64_to_pil(output["mask_b64"])
    hist_img = _b64_to_pil(output["histogram_b64"])

    stats_text = (
        f"### 📊 Statistics\n\n"
        f"**Cell Count:** {output['cell_count']}\n\n"
        f"**Confluency:** {output['confluency']:.2f}%\n\n"
        f"**Min Intensity:** {output['min_intensity']}\n\n"
        f"**Max Intensity:** {output['max_intensity']}"
    )
    return norm_img, mask_img, hist_img, stats_text


# ----------------- Gradio UI -----------------

with gr.Blocks() as demo:
    gr.Markdown("## 🧪 Fibroblast Confluency detection (RunPod Serverless backend)")

    with gr.Row():
        with gr.Column():
            image_input = gr.Image(type="pil", label="Upload Image")
            diameter_slider = gr.Slider(minimum=5, maximum=100, step=1, value=30,
                                         label="Approx. Cell Diameter")
            denoise_checkbox = gr.Checkbox(label="Apply Denoising")
            blur_checkbox = gr.Checkbox(label="Apply Gaussian Blur")
            run_btn = gr.Button("Run Detection", variant="primary")

        with gr.Column():
            stats_output = gr.Markdown(label="Statistics")
            output1 = gr.Image(label="Normalized Image", interactive=True)
            output2 = gr.Image(label="Segmentation Mask", interactive=True, height=300)
            output3 = gr.Image(label="Intensity Histogram", interactive=True)

    run_btn.click(
        fn=process_image,
        inputs=[image_input, diameter_slider, denoise_checkbox, blur_checkbox],
        outputs=[output1, output2, output3, stats_output],
    )


if __name__ == "__main__":
    server_name = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
    server_port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    share = os.getenv("GRADIO_SHARE", "false").lower() == "true"

    if not (RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID):
        print(
            "[warn] RUNPOD_API_KEY and/or RUNPOD_ENDPOINT_ID are not set. "
            "The UI will load but inference calls will fail until they are "
            "configured."
        )

    demo.queue(default_concurrency_limit=4).launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
        show_error=True,
    )
