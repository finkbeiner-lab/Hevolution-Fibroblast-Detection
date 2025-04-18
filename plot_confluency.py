import cv2
import numpy as np
import matplotlib.pyplot as plt

# Load the original image and masks
original_image = cv2.imread('/Users/vgopalramaswamy/Downloads/AG04054B_2.jpg', cv2.IMREAD_UNCHANGED)
mask = cv2.imread('/Users/vgopalramaswamy/Downloads/AG04054B_2_cp_masks.png', cv2.IMREAD_UNCHANGED)

# Convert the mask to binary: any non-zero value is considered part of a cell
binary_mask = np.where(mask > 0, 1, 0).astype(np.uint8)

# Calculate cell confluence as the percentage of non-zero pixels
masked_area = np.sum(binary_mask)
total_area = binary_mask.size
confluence = (masked_area / total_area) * 100

# Count number of blobs (connected components excluding background)
num_labels, _ = cv2.connectedComponents(binary_mask)
num_cells = num_labels - 1  # Subtract 1 for background label (0)

print(f"Cell Confluence: {confluence:.2f}%")
print(f"Number of Cells (Blobs): {num_cells}")

# Convert to grayscale for histogram (handle both grayscale and color images)
if len(original_image.shape) == 3 and original_image.shape[2] == 3:
    gray_image = cv2.cvtColor(original_image, cv2.COLOR_BGR2GRAY)
else:
    gray_image = original_image.copy()

# Compute histogram of grayscale image
hist = cv2.calcHist([gray_image], [0], None, [256], [0, 256])
hist = hist.ravel()

# Get min and max intensity values
min_intensity = np.min(gray_image)
max_intensity = np.max(gray_image)

# Plotting
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle(f'Cell Confluence: {confluence:.2f}% | Number of Cells: {num_cells}', fontsize=16, weight='bold')

# Original image
axes[0, 0].imshow(cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB) if len(original_image.shape) == 3 else original_image, cmap='gray')
axes[0, 0].set_title('Original Image')
axes[0, 0].axis('off')

# Encoded mask
axes[0, 1].imshow(mask, cmap='jet')
axes[0, 1].set_title('Original Encoded Mask')
axes[0, 1].axis('off')

# Binary mask
axes[1, 0].imshow(binary_mask, cmap='gray')
axes[1, 0].set_title('Binary Mask')
axes[1, 0].axis('off')

# Histogram
axes[1, 1].plot(hist, color='black')
axes[1, 1].set_title('Grayscale Intensity Histogram')
axes[1, 1].set_xlim([0, 255])
axes[1, 1].set_xlabel('Pixel Intensity')
axes[1, 1].set_ylabel('Frequency')
axes[1, 1].text(0.95, 0.95, f'Min: {min_intensity}\nMax: {max_intensity}', transform=axes[1, 1].transAxes,
                fontsize=12, verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', edgecolor='gray'))

plt.tight_layout(rect=[0, 0, 1, 0.95])
plt.show()
