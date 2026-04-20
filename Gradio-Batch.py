import os
import numpy as np
from cellpose import models
from PIL import Image
import cv2
import matplotlib.pyplot as plt
import io
import gradio as gr

# ----------------- Image Preprocessing Functions -----------------

def denoise_image(img, h=10):
    img = np.clip(img, 0, 255)
    img = img.astype(np.uint8)
    if img.ndim == 2:
        return cv2.fastNlMeansDenoising(img, h=h)
    elif img.ndim == 3 and img.shape[2] == 3:
        return cv2.fastNlMeansDenoisingColored(img, None, h, h, 7, 21)
    else:
        return img

def apply_gaussian_blur(img, ksize=(5, 5), sigma=1.0):
    return cv2.GaussianBlur(img, ksize, sigmaX=sigma)

def normalize_image(img):
    p1, p99 = np.percentile(img, (1, 99))
    img = np.clip((img - p1) / (p99 - p1 + 1e-8), 0, 1)
    return (img * 255).astype(np.uint8)

# ----------------- Matplotlib to PIL -----------------

def fig_to_image(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf)

def visualize_outputs_with_matplotlib(norm_gray, masks):
    fig1, ax1 = plt.subplots(figsize=(4, 4))
    ax1.imshow(norm_gray, cmap='gray')
    ax1.set_title("Normalized Image")
    ax1.axis("off")
    norm_img = fig_to_image(fig1)

    fig2, ax2 = plt.subplots(figsize=(4, 4))
    ax2.imshow(masks, cmap='nipy_spectral')
    ax2.set_title("Segmentation Mask")
    ax2.axis("off")
    mask_img = fig_to_image(fig2)

    fig3, ax3 = plt.subplots(figsize=(4, 3))
    ax3.hist(norm_gray.ravel(), bins=256, range=(0, 255), color='gray', edgecolor='black')
    ax3.set_title("Intensity Histogram")
    ax3.set_xlabel("Pixel Intensity")
    ax3.set_ylabel("Frequency")
    hist_img = fig_to_image(fig3)

    return norm_img, mask_img, hist_img

# ----------------- Core Processing -----------------

def compute_statistics(masks, norm_gray):
    cell_labels = np.unique(masks)
    cell_labels = cell_labels[cell_labels != 0]  # Exclude background
    cell_count = len(cell_labels)

    confluency = 100.0 * np.count_nonzero(masks) / masks.size

    min_intensity = int(norm_gray.min())
    max_intensity = int(norm_gray.max())

    stats_text = (
        f"### 📊 Statistics\n\n"
        f"**Cell Count:** {cell_count}\n\n"
        f"**Confluency:** {confluency:.2f}%\n\n"
        f"**Min Intensity:** {min_intensity}\n\n"
        f"**Max Intensity:** {max_intensity}"
    )
    return stats_text

def process_image(image, diameter=None, denoise=False, blur=False):
    img = np.array(image)

    # Convert to grayscale if RGB
    if img.ndim == 3 and img.shape[2] == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img.copy()

    if denoise:
        gray = denoise_image(gray)
    if blur:
        gray = apply_gaussian_blur(gray)

    norm_gray = normalize_image(gray)

    model = models.Cellpose(gpu=True, model_type='cyto3')
    masks, flows, styles, diams = model.eval(norm_gray, diameter=diameter, channels=[0, 0])

    norm_img, mask_img, hist_img = visualize_outputs_with_matplotlib(norm_gray, masks)
    stats_text = compute_statistics(masks, norm_gray)

    return norm_img, mask_img, hist_img, stats_text

# ----------------- Gradio UI -----------------

with gr.Blocks() as demo:
    gr.Markdown("## 🧪 Fibroblast Confluency detection with Matplotlib Visualizations")

    with gr.Row():
        with gr.Column():
            image_input = gr.Image(type="pil", label="Upload Image")
            diameter_slider = gr.Slider(minimum=5, maximum=100, step=1, value=30, label="Approx. Cell Diameter")
            denoise_checkbox = gr.Checkbox(label="Apply Denoising")
            blur_checkbox = gr.Checkbox(label="Apply Gaussian Blur")
            run_btn = gr.Button("Run Detection")

        with gr.Column():
            stats_output = gr.Markdown(label="Statistics")
            output1 = gr.Image(label="Normalized Image", interactive=True)
            output2 = gr.Image(label="Segmentation Mask", interactive=True,  height=300)
            output3 = gr.Image(label="Intensity Histogram", interactive=True)

    run_btn.click(
        fn=process_image,
        inputs=[image_input, diameter_slider, denoise_checkbox, blur_checkbox],
        outputs=[output1, output2, output3, stats_output]
    )

if __name__ == "__main__":
    # Allow configuration via environment variables for deployment
    server_name = os.getenv("GRADIO_SERVER_NAME", "127.0.0.1")
    server_port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    share = os.getenv("GRADIO_SHARE", "False").lower() == "true"
    
    demo.launch(
        server_name=server_name,
        server_port=server_port,
        share=share
    )
