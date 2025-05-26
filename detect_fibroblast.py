import os
import numpy as np
from cellpose import models
import imageio
from tqdm import tqdm
from PIL import Image
import cv2
import matplotlib.pyplot as plt

# def denoise_image(img, h=10):
#     if img.ndim == 2:
#         return cv2.fastNlMeansDenoising(img, h=h)
#     elif img.ndim == 3 and img.shape[2] == 3:
#         return cv2.fastNlMeansDenoisingColored(img, None, h, h, 7, 21)
#     return img

def denoise_image(img, h=10):
    """
    Applies non-local means denoising.
    """
    img = np.clip(img, 0, 255)  # Ensure values are in a valid range
    img = img.astype(np.uint8)  # Convert to uint8

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

def run_cellpose_on_folder(folder_path, model_type='cyto3', diameter=None, save_dir='masks',
                           denoise=False, gaussian_blur=False, visualize=False):
    valid_exts = ['.tif', '.tiff', '.jpg', '.jpeg', '.png']
    os.makedirs(save_dir, exist_ok=True)

    model = models.Cellpose(gpu=True, model_type=model_type)
    image_files = [f for f in os.listdir(folder_path) if os.path.splitext(f)[1].lower() in valid_exts]

    for img_name in tqdm(image_files, desc="Processing images"):
        img_path = os.path.join(folder_path, img_name)
        base_name = os.path.splitext(img_name)[0]

        img = imageio.imread(img_path)

        # Grayscale if needed
        if img.ndim == 3 and img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Optional preprocessing
        if denoise:
            img = denoise_image(img)
        if gaussian_blur:
            img = apply_gaussian_blur(img)
        
        img = normalize_image(img)

        # Run Cellpose
        masks, flows, styles, diams = model.eval(
            img,
            diameter=diameter,
            channels=[0, 0],
            resample=True,
            flow_threshold=0.4,
            cellprob_threshold=0.0,
            do_3D=False
        )

        # Save encoded mask
        encoded_mask_path = os.path.join(save_dir, f"{base_name}_mask.png")
        Image.fromarray(masks.astype(np.uint16)).save(encoded_mask_path)

        print(f"Saved encoded mask: {encoded_mask_path}")

        # Optional side-by-side visualization
        if visualize:
            plt.figure(figsize=(10, 5))
            plt.subplot(1, 2, 1)
            plt.title("Input")
            plt.imshow(img, cmap='gray')
            plt.axis('off')
            plt.subplot(1, 2, 2)
            plt.title("Mask")
            plt.imshow(masks, cmap='gray')
            plt.axis('off')
            plt.tight_layout()
            plt.show()

# 🔧 CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Cellpose on all images in a folder.")
    parser.add_argument("folder_path", type=str, help="Path to folder with input images")
    parser.add_argument("--diameter", type=float, default=None, help="Approx. cell diameter (optional)")
    parser.add_argument("--model", type=str, default="cyto3", help="Model type: cyto, cyto3, nuclei, etc.")
    parser.add_argument("--save_dir", type=str, default="masks", help="Directory to save mask outputs")
    parser.add_argument("--denoise", action="store_true", help="Apply denoising to input images before segmentation")
    parser.add_argument("--gaussian_blur", action="store_true", help="Apply Gaussian blur before segmentation")
    parser.add_argument("--visualize", action="store_true", help="Show input vs. mask side-by-side")

    args = parser.parse_args()

    run_cellpose_on_folder(
        folder_path=args.folder_path,
        model_type=args.model,
        diameter=args.diameter,
        save_dir=args.save_dir,
        denoise=args.denoise,
        gaussian_blur=args.gaussian_blur,
        visualize=args.visualize
    )
