import os
import numpy as np
from cellpose import models
import imageio
from tqdm import tqdm
from PIL import Image
import cv2

def denoise_image(img, h=10):
    """
    Applies non-local means denoising.
    """
    if img.ndim == 2:
        return cv2.fastNlMeansDenoising(img, h=h)
    elif img.ndim == 3 and img.shape[2] == 3:
        return cv2.fastNlMeansDenoisingColored(img, None, h, h, 7, 21)
    else:
        return img

def apply_gaussian_blur(img, ksize=(5, 5), sigma=1.0):
    """
    Applies Gaussian blur to an image.
    """
    return cv2.GaussianBlur(img, ksize, sigmaX=sigma)

def run_cellpose_on_folder(folder_path, model_type='cyto3', diameter=None, save_dir='masks',
                           denoise=False, gaussian_blur=False):
    """
    Runs Cellpose segmentation on all image files in a folder and saves encoded masks as 16-bit PNGs.

    Parameters:
        folder_path (str): Directory containing images.
        model_type (str): 'cyto', 'nuclei', etc.
        diameter (float or None): Approx. cell diameter.
        save_dir (str): Directory where mask outputs will be saved.
        denoise (bool): Apply non-local means denoising before segmentation.
        gaussian_blur (bool): Apply Gaussian blur before segmentation.
    """
    valid_exts = ['.tif', '.tiff', '.jpg', '.jpeg', '.png']
    os.makedirs(save_dir, exist_ok=True)

    model = models.Cellpose(gpu=True, model_type=model_type)
    image_files = [f for f in os.listdir(folder_path) if os.path.splitext(f)[1].lower() in valid_exts]

    for img_name in tqdm(image_files, desc="Processing images"):
        img_path = os.path.join(folder_path, img_name)
        base_name = os.path.splitext(img_name)[0]

        img = imageio.imread(img_path)

        # Optional preprocessing
        if denoise:
            img = denoise_image(img)
        if gaussian_blur:
            img = apply_gaussian_blur(img)

        # Run Cellpose
        masks, flows, styles, diams = model.eval(img, diameter=diameter, channels=[0, 0])

        # Save encoded mask as 16-bit PNG (each object has a unique integer label)
        encoded_mask_path = os.path.join(save_dir, f"{base_name}_mask.png")
        Image.fromarray(masks.astype(np.uint16)).save(encoded_mask_path)

        print(f"Saved encoded mask: {encoded_mask_path}")

# 🔧 Command-line interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Cellpose on all images in a folder.")
    parser.add_argument("folder_path", type=str, help="Path to folder with input images")
    parser.add_argument("--diameter", type=float, default=None, help="Approx. cell diameter (optional)")
    parser.add_argument("--model", type=str, default="cyto", help="Model type: cyto, nuclei, etc.")
    parser.add_argument("--save_dir", type=str, default="masks", help="Directory to save mask outputs")
    parser.add_argument("--denoise", action="store_true", help="Apply denoising to input images before segmentation")
    parser.add_argument("--gaussian_blur", action="store_true", help="Apply Gaussian blur before segmentation")

    args = parser.parse_args()

    run_cellpose_on_folder(
        folder_path=args.folder_path,
        model_type=args.model,
        diameter=args.diameter,
        save_dir=args.save_dir,
        denoise=args.denoise,
        gaussian_blur=args.gaussian_blur
    )
