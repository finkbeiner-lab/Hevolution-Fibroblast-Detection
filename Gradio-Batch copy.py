import os
import io
import zipfile
import numpy as np
import pandas as pd
from cellpose import models
from PIL import Image
import cv2
import matplotlib.pyplot as plt
import gradio as gr

def denoise_image(img, h=10):
    img = np.clip(img, 0, 255).astype(np.uint8)
    if img.ndim == 2:
        return cv2.fastNlMeansDenoising(img, h=h)
    elif img.ndim == 3 and img.shape[2] == 3:
        return cv2.fastNlMeansDenoisingColored(img, None, h, h, 7, 21)
    return img

def apply_gaussian_blur(img, ksize=(5, 5), sigma=1.0):
    return cv2.GaussianBlur(img, ksize, sigmaX=sigma)

def normalize_image(img):
    p1, p99 = np.percentile(img, (1, 99))
    img = np.clip((img - p1) / (p99 - p1 + 1e-8), 0, 1)
    return (img * 255).astype(np.uint8)

def process_image(img, model, diameter=None, denoise=False, gaussian=False, file_id="image"):
    img = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    min_contrast = int(gray.min())
    max_contrast = int(gray.max())

    if denoise:
        gray = denoise_image(gray)
    if gaussian:
        gray = apply_gaussian_blur(gray)

    gray_norm = normalize_image(gray)

    masks, flows, styles, diams = model.eval(
        gray_norm,
        diameter=diameter,
        channels=[0, 0],
        resample=True,
        flow_threshold=0.4,
        cellprob_threshold=0.0,
        do_3D=False
    )

    unique_ids = np.unique(masks[masks > 0])
    total_count = len(unique_ids)

    # Plot histogram of cell sizes
    fig, ax = plt.subplots(figsize=(4, 2.5))
    if total_count > 0:
        areas = [(masks == i).sum() for i in unique_ids]
        ax.hist(areas, bins=20, color='teal', edgecolor='black')
    ax.set_title("Cell Size Histogram")
    ax.set_xlabel("Pixel Area")
    ax.set_ylabel("Frequency")
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    hist_img = Image.open(buf)

    # Color mask for display
    mask_disp = (masks > 0).astype(np.uint8) * 255
    mask_rgb = cv2.applyColorMap(mask_disp, cv2.COLORMAP_JET)
    mask_img = Image.fromarray(mask_rgb)

    summary_row = {
        "Filename": file_id,
        "Total Count": total_count,
        "Min Contrast": min_contrast,
        "Max Contrast": max_contrast
    }

    return gray_norm, mask_img, hist_img, masks, summary_row

def batch_segment(files, model_type, diameter, denoise, gaussian):
    model = models.Cellpose(gpu=True, model_type=model_type)

    results = []
    summary_rows = []

    zip_dir = "temp_results"
    os.makedirs(zip_dir, exist_ok=True)

    for file_obj in files:
        filename = os.path.basename(file_obj.name)
        img = Image.open(file_obj.name)
        gray_norm, mask_img, hist_img, masks, summary_row = process_image(
            img, model, diameter, denoise, gaussian, filename
        )

        # Save mask and histogram images to temp folder for zipping
        mask_path = os.path.join(zip_dir, f"{filename}_mask.png")
        hist_path = os.path.join(zip_dir, f"{filename}_hist.png")

        mask_img.save(mask_path)
        hist_img.save(hist_path)

        summary_rows.append(summary_row)
        results.append((gray_norm, mask_img, hist_img, filename))

    # Create summary CSV
    summary_df = pd.DataFrame(summary_rows)
    summary_csv_path = os.path.join(zip_dir, "summary.csv")
    summary_df.to_csv(summary_csv_path, index=False)

    # Zip all results
    zip_path = os.path.join(zip_dir, "results.zip")
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for f in os.listdir(zip_dir):
            if f != "results.zip":
                zipf.write(os.path.join(zip_dir, f), arcname=f)

    # For UI, return first image results for display + zip download
    if results:
        first_gray, first_mask, first_hist, first_name = results[0]
    else:
        first_gray = first_mask = first_hist = None

    return first_gray, first_mask, first_hist, zip_path

with gr.Blocks() as demo:
    gr.Markdown("## Cellpose Batch Segmentation with Summary CSV and ZIP download")

    with gr.Row():
        file_input = gr.File(label="Upload images (multiple allowed)", file_types=[".png", ".jpg", ".jpeg", ".tif", ".tiff"], file_count="multiple")
        with gr.Column():
            model_type = gr.Dropdown(choices=["cyto", "cyto3", "nuclei"], value="cyto3", label="Cellpose Model Type")
            diameter = gr.Number(value=None, precision=1, label="Cell Diameter (optional)", interactive=True)
            denoise = gr.Checkbox(label="Apply Denoising", value=False)
            gaussian = gr.Checkbox(label="Apply Gaussian Blur", value=False)
            run_btn = gr.Button("Run Segmentation")

    gray_out = gr.Image(label="Normalized Grayscale Image")
    mask_out = gr.Image(label="Cellpose Mask (Colored)")
    hist_out = gr.Image(label="Cell Size Histogram")
    download_zip = gr.File(label="Download ZIP with all results")

    def run_all(files, model_type, diameter, denoise, gaussian):
        diameter_val = float(diameter) if diameter else None
        return batch_segment(files, model_type, diameter_val, denoise, gaussian)

    run_btn.click(
        run_all,
        inputs=[file_input, model_type, diameter, denoise, gaussian],
        outputs=[gray_out, mask_out, hist_out, download_zip]
    )

demo.launch()
