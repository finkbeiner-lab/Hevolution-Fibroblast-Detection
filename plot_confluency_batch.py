import os
import numpy as np
import cv2
import matplotlib.pyplot as plt
from glob import glob
import pdb

def calculate_and_plot_confluence(image_path, mask_path, save_dir):
    os.makedirs(save_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(image_path))[0]

    # Load image and mask
    original_image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    mask = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)

    # Convert to binary mask (non-zero = cell area)
    binary_mask = np.where(mask > 0, 1, 0)

    # Calculate confluence
    masked_area = np.sum(binary_mask)
    total_area = mask.size
    confluence = (masked_area / total_area) * 100

    # Plot
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle(f'{base_name} - Cell Confluence: {confluence:.2f}%', fontsize=16, weight='bold')

    axes[0].imshow(cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB))
    axes[0].set_title('Original Image')
    axes[0].axis('off')

    axes[1].imshow(mask, cmap='jet')
    axes[1].set_title('Encoded Mask')
    axes[1].axis('off')

    axes[2].imshow(binary_mask, cmap='gray')
    axes[2].set_title('Binary Mask')
    axes[2].axis('off')
    axes[2].text(0.5, 0.95, f'{confluence:.2f}%', ha='center', va='top',
                 color='white', fontsize=12, weight='bold', transform=axes[2].transAxes)

    plt.tight_layout()
    save_path = os.path.join(save_dir, f'{base_name}_confluence_plot.png')
    plt.savefig(save_path)
    plt.close()
    print(f"Saved confluence plot: {save_path}")

def process_folder(image_folder, mask_folder, save_dir='plots'):
    # Assumes mask filenames follow pattern: <name>_cp_masks.png
    image_paths = sorted(glob(os.path.join(image_folder, '*.jpg')))
    
    for image_path in image_paths:
        base = os.path.splitext(os.path.basename(image_path))[0]
        mask_path = os.path.join(mask_folder, f'{base}_mask.png')

        if os.path.exists(mask_path):
            calculate_and_plot_confluence(image_path, mask_path, save_dir)
        else:
            print(f"Mask not found for image: {image_path}")

# 🔧 Example usage
if __name__ == "__main__":
    image_folder = "/home/vgramas/Desktop/steve/work/data/Hevolution/Austin-Fibroblasts"
    mask_folder = "/home/vgramas/Desktop/steve/work/data/Hevolution/Austin-Fibroblasts/masks"
    save_dir = "plots"

    process_folder(image_folder, mask_folder, save_dir)
