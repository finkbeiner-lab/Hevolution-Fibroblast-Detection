import numpy as np
import pdb

# # Load the .npy file with allow_pickle=True
# x = np.load("/Volumes/Finkbeiner-Steve/work/data/Hevolution/Austin-Fibroblasts/AG08498A-P14_T25_10X_0000_TRANS_seg.npy", allow_pickle=True)
# pdb.set_trace()
# mask = ['masks']

import cv2
import numpy as np
import matplotlib.pyplot as plt


# Load the image or mask (assuming it's a binary mask)
original_image = cv2.imread('/Volumes/Finkbeiner-Steve/work/data/Hevolution/Austin-Fibroblasts/AG08498A-P14_T25_10X_0000_TRANS.jpg', cv2.IMREAD_UNCHANGED)
mask = cv2.imread('/Volumes/Finkbeiner-Steve/work/data/Hevolution/Austin-Fibroblasts/AG08498A-P14_T25_10X_0000_TRANS_cp_masks.png', cv2.IMREAD_UNCHANGED)
# Convert the mask to binary: any non-zero value is considered part of the cell
binary_mask = np.where(mask > 0, 1, 0)

# Calculate the area covered by cells (non-zero pixels in binary mask)
masked_area = np.sum(binary_mask)

# Get the total number of pixels in the image (height * width)
total_area = mask.size

# Calculate confluence as a percentage
confluence = (masked_area / total_area) * 100

print(f"Cell Confluence: {confluence}%")

# Plot the original image, encoded mask, and binary mask side by side
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# Set the title for the entire figure
fig.suptitle(f'Cell Confluence: {confluence:.2f}%', fontsize=16, weight='bold')

# Plot the original image
axes[0].imshow(cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB))  # Convert BGR to RGB for proper display
axes[0].set_title('Original Image')
axes[0].axis('off')  # Turn off axis

# Plot the original encoded mask
axes[1].imshow(mask, cmap='jet')  # Using 'jet' colormap for better color visibility
axes[1].set_title('Original Encoded Mask')
axes[1].axis('off')  # Turn off axis

# Plot the binary mask
axes[2].imshow(binary_mask, cmap='gray')  # Using 'gray' for binary
axes[2].set_title('Binary Mask')
axes[2].axis('off')  # Turn off axis

# Add text with confluence value to the plot
axes[2].text(0.5, 0.95, f'Confluence: {confluence:.2f}%', ha='center', va='top', color='white', fontsize=12, weight='bold')

# Show the plots
plt.tight_layout()
plt.show()
