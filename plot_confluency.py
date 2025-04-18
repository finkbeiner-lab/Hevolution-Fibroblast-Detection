import cv2
import numpy as np
import matplotlib.pyplot as plt

# Load the original image and masks
original_image = cv2.imread('/Volumes/Finkbeiner-Steve/work/data/Hevolution/Austin-Fibroblasts/AG08498A-P14_T25_10X_0000_TRANS.jpg', cv2.IMREAD_UNCHANGED)
mask = cv2.imread('/Volumes/Finkbeiner-Steve/work/data/Hevolution/Austin-Fibroblasts/AG08498A-P14_T25_10X_0000_TRANS_cp_masks.png', cv2.IMREAD_UNCHANGED)
cell_mask = cv2.imread('/Volumes/Finkbeiner-Steve/work/data/Hevolution/Austin-Fibroblasts/AG08498A-P14_T25_10X_0000_TRANS_cell_masks.png', cv2.IMREAD_UNCHANGED)

# Convert the mask to binary: any non-zero value is considered part of a cell
binary_mask = np.where(mask > 0, 1, 0)

# Calculate cell confluence as the percentage of non-zero pixels
masked_area = np.sum(binary_mask)
total_area = mask.size
confluence = (masked_area / total_area) * 100

# Count number of unique cell masks (assuming each cell is a uniquely labeled region)
num_cells = len(np.unique(cell_mask)) - 1  # Subtract 1 for background (0)

print(f"Cell Confluence: {confluence:.2f}%")
print(f"Number of Cells: {num_cells}")

# Plotting
fig, axes = plt.subplots(1, 3, figsize=(18, 6))
fig.suptitle(f'Cell Confluence: {confluence:.2f}% | Number of Cells: {num_cells}', fontsize=16, weight='bold')

# Original image
axes[0].imshow(cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB))
axes[0].set_title('Original Image')
axes[0].axis('off')

# Encoded mask
axes[1].imshow(mask, cmap='jet')
axes[1].set_title('Original Encoded Mask')
axes[1].axis('off')

# Binary mask with annotations
axes[2].imshow(binary_mask, cmap='gray')
axes[2].set_title('Binary Mask')
axes[2].axis('off')


plt.tight_layout()
plt.show()
