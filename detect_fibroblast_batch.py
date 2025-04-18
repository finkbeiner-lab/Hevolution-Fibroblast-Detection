import os
import numpy as np
from cellpose import models
import imageio
from tqdm import tqdm
from cellpose.plot import mask_rgb
from PIL import Image
import cv2

def denoise_image(img, h=10):
    if img.ndim == 2:
        return cv2.fastNlMeansDenoising(img, h=h)
    elif img.ndim == 3 and img.shape[2] == 3:
        return cv2.fastNlMeansDenoisingColored(img, None, h, h, 7, 21)
    else:
        return img

def run_cellpose_batch(folder_path, model_type='cyto', diameter=None, save_dir='masks', denoise=False):
    valid_exts = ['.tif', '.tiff', '.jpg', '.jpeg', '.png']
    os.makedirs(save_dir, exist_ok=True)

    # Collect image paths
    image_paths = [
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in valid_exts
    ]

    # Load and optionally denoise all images
    images = []
    base_names = []

    print("Loading and preprocessing images...")
    for img_path in tqdm(image_paths):
        img = imageio.imread(img_path)
        if denoise:
            img = denoise_image(img, h=10)
        images.append(img)
        base_names.append(os.path.splitext(os.path.basename(img_path))[0])

    print(f"Running Cellpose on {len(images)} images as a batch...")
    model = models.Cellpose(gpu=False, model_type=model_type)
    masks_list, flows_list, styles, diams = model.eval(
        images, diameter=diameter, channels=[0, 0]
    )

    print("Saving results...")
    for base_name, masks in zip(base_names, masks_list):
        rgb_mask = mask_rgb(masks)
        rgb_mask_img = Image.fromarray((rgb_mask * 255).astype(np.uint8))
        rgb_mask_img.save(os.path.join(save_dir, f"{base_name}_mask.png"))

# 🔧 CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Batch run Cellpose on images in a folder.")
    parser.add_argument("folder_path", type=str, help="Path to folder with input images")
    parser.add_argument("--diameter", type=float, default=None, help="Approx. cell diameter")
    parser.add_argument("--model", type=str, default="cyto", help="Model type: cyto, nuclei, etc.")
    parser.add_argument("--save_dir", type=str, default="masks", help="Where to save mask outputs")
    parser.add_argument("--denoise", action="store_true", help="Denoise images before segmentation")

    args = parser.parse_args()

    run_cellpose_batch(
        folder_path=args.folder_path,
        model_type=args.model,
        diameter=args.diameter,
        save_dir=args.save_dir,
        denoise=args.denoise
    )
