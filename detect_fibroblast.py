import os
import numpy as np
import matplotlib.pyplot as plt
from cellpose import models, io
import imageio
from tqdm import tqdm
from cellpose.plot import mask_rgb
from PIL import Image

def run_cellpose_on_folder(folder_path, model_type='cyto', diameter=None, save_dir='masks'):
    """
    Runs Cellpose segmentation on all image files in a folder.

    Parameters:
        folder_path (str): Directory containing images.
        model_type (str): 'cyto', 'nuclei', etc.
        diameter (float or None): Approx. cell diameter.
        save_dir (str): Directory where mask outputs will be saved.
    """
    # Supported image formats
    valid_exts = ['.tif', '.tiff', '.jpg', '.jpeg', '.png']

    # Make sure save directory exists
    os.makedirs(save_dir, exist_ok=True)

    # Initialize Cellpose model
    model = models.Cellpose(gpu=True, model_type=model_type)

    # Loop over image files
    image_files = [f for f in os.listdir(folder_path) if os.path.splitext(f)[1].lower() in valid_exts]

    for img_name in tqdm(image_files, desc="Processing images"):
        img_path = os.path.join(folder_path, img_name)
        base_name = os.path.splitext(img_name)[0]

        # Load image
        img = imageio.imread(img_path)

        # Run Cellpose
        masks, flows, styles, diams = model.eval(
            img, diameter=diameter, channels=[0, 0]
        )

        # Save mask as PNG (colored)
        rgb_mask = mask_rgb(masks)
        rgb_mask_img = Image.fromarray((rgb_mask * 255).astype(np.uint8))
        rgb_mask_img.save(os.path.join(save_dir, f"{base_name}_mask.png"))

        print(f"Saved mask for: {img_name}")

# 🔧 Command-line interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Cellpose on all images in a folder.")
    parser.add_argument("folder_path", type=str, help="Path to folder with input images")
    parser.add_argument("--diameter", type=float, default=None, help="Approx. cell diameter (optional)")
    parser.add_argument("--model", type=str, default="cyto", help="Model type: cyto, nuclei, etc.")
    parser.add_argument("--save_dir", type=str, default="masks", help="Directory to save mask outputs")

    args = parser.parse_args()

    run_cellpose_on_folder(
        folder_path=args.folder_path,
        model_type=args.model,
        diameter=args.diameter,
        save_dir=args.save_dir
    )
