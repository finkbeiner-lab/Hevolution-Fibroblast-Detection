"""
SageMaker Inference Handler for Fibroblast Detection
"""

import os
import json
import numpy as np
from PIL import Image
import cv2
import matplotlib.pyplot as plt
import io
import base64
import logging

# Import Cellpose - Cellpose 3.0+ uses CellposeModel
from cellpose import models

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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

# ----------------- Helper Functions -----------------

def fig_to_image(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf)

def image_to_base64(img):
    """Convert PIL Image to base64 string"""
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

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

def compute_statistics(masks, norm_gray):
    cell_labels = np.unique(masks)
    cell_labels = cell_labels[cell_labels != 0]  # Exclude background
    cell_count = len(cell_labels)

    confluency = 100.0 * np.count_nonzero(masks) / masks.size

    min_intensity = int(norm_gray.min())
    max_intensity = int(norm_gray.max())

    stats = {
        "cell_count": int(cell_count),
        "confluency": float(confluency),
        "min_intensity": int(min_intensity),
        "max_intensity": int(max_intensity)
    }
    return stats

# ----------------- SageMaker Handler Functions -----------------

# Global model variable - will be initialized by model_fn
_model_cache = None

def model_fn(model_dir):
    """
    Load the Cellpose model. Called once when endpoint starts.
    """
    global _model_cache
    
    logger.info(f"Loading model from directory: {model_dir}")
    logger.info(f"Files in model_dir: {os.listdir(model_dir) if os.path.exists(model_dir) else 'Directory does not exist'}")
    
    try:
        # Check GPU availability
        import torch
        gpu_available = torch.cuda.is_available()
        logger.info(f"GPU available: {gpu_available}")
        
        # Initialize Cellpose model - Cellpose 3.0+ uses CellposeModel
        logger.info("Initializing Cellpose model (cyto3)...")
        # Cellpose 3.0+ API: models.CellposeModel
        # Disable BFloat16 to avoid "upsample_linear1d_out_frame" not implemented error
        # This is a known issue with PyTorch 2.0.1 and certain CUDA versions
        _model_cache = models.CellposeModel(
            model_type='cyto3', 
            gpu=gpu_available,
            use_bfloat16=False  # Disable BFloat16 to avoid CUDA errors
        )
        logger.info("✅ Cellpose model loaded successfully")
        
        return _model_cache
        
    except Exception as e:
        logger.error(f"❌ Error loading model: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

def input_fn(request_body, request_content_type='application/json'):
    """
    Deserialize and prepare the prediction input.
    """
    logger.info(f"Received request with content type: {request_content_type}")
    logger.info(f"Request body type: {type(request_body)}")
    logger.info(f"Request body length: {len(request_body) if hasattr(request_body, '__len__') else 'N/A'}")
    
    try:
        # Handle case where request_body is already a dict (parsed by sagemaker-inference)
        if isinstance(request_body, dict):
            logger.info("Request body is already a dict")
            input_data = request_body
        elif isinstance(request_body, bytes):
            # Handle bytes input
            logger.info("Request body is bytes, decoding...")
            request_body = request_body.decode('utf-8')
            input_data = json.loads(request_body)
        elif isinstance(request_body, str):
            # Handle string input
            logger.info("Request body is string, parsing JSON...")
            if len(request_body) == 0:
                raise ValueError("Empty request body")
            input_data = json.loads(request_body)
        else:
            raise ValueError(f"Unexpected request body type: {type(request_body)}")
        
        logger.info(f"Parsed input_data keys: {list(input_data.keys()) if isinstance(input_data, dict) else 'N/A'}")
        
        # Handle health check/ping requests (empty or ping requests)
        if not input_data or input_data == {} or input_data.get('health_check') or 'ping' in str(input_data).lower():
            logger.info("Health check/ping request detected, returning empty response")
            return {'health_check': True}
        
        # Extract parameters
        image_data = input_data.get('image')
        if not image_data:
            logger.error(f"Missing 'image' field. Available keys: {list(input_data.keys())}")
            logger.error(f"Input data sample: {str(input_data)[:200]}")
            raise ValueError("Missing 'image' field in request")
        
        diameter = input_data.get('diameter', None)
        denoise = input_data.get('denoise', False)
        blur = input_data.get('blur', False)
        
        logger.info(f"Input parameters - diameter: {diameter}, denoise: {denoise}, blur: {blur}")
        logger.info(f"Image data length: {len(image_data) if image_data else 0}")
        
        return {
            'image': image_data,
            'diameter': diameter,
            'denoise': denoise,
            'blur': blur
        }
            
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        logger.error(f"Request body (first 500 chars): {str(request_body)[:500]}")
        raise ValueError(f"Invalid JSON in request body: {str(e)}")
    except Exception as e:
        logger.error(f"Error in input_fn: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

def predict_fn(input_data, model):
    """
    Perform prediction on the deserialized input.
    """
    try:
        logger.info("Starting prediction...")
        
        # Handle health check requests
        if input_data.get('health_check'):
            logger.info("Health check request, skipping prediction")
            return {'status': 'healthy'}
        
        # Decode base64 image
        image_data = input_data.get('image')
        if not image_data:
            raise ValueError("Missing 'image' field in input_data")
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        logger.info(f"Image loaded: {image.size}, mode: {image.mode}")
        
        img = np.array(image)

        # Convert to grayscale if RGB
        if img.ndim == 3 and img.shape[2] == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            gray = img.copy()

        # Apply preprocessing
        if input_data.get('denoise', False):
            logger.info("Applying denoising...")
            gray = denoise_image(gray)
            
        if input_data.get('blur', False):
            logger.info("Applying Gaussian blur...")
            gray = apply_gaussian_blur(gray)

        # Normalize
        norm_gray = normalize_image(gray)
        logger.info("Image normalized")

        # Run Cellpose segmentation
        logger.info("Running Cellpose segmentation...")
        diameter = input_data.get('diameter')
        
        # Cellpose 3.0+ may return 3 or 4 values depending on version
        eval_result = model.eval(
            norm_gray, 
            diameter=diameter, 
            channels=[0, 0]
        )
        
        # Handle different return formats
        if len(eval_result) == 4:
            masks, flows, styles, diams = eval_result
            logger.info(f"Segmentation complete. Detected diameter: {diams}")
        elif len(eval_result) == 3:
            masks, flows, styles = eval_result
            diams = diameter if diameter else None
            logger.info(f"Segmentation complete. Using diameter: {diams}")
        else:
            raise ValueError(f"Unexpected number of return values from model.eval(): {len(eval_result)}")

        # Generate visualizations
        logger.info("Generating visualizations...")
        norm_img, mask_img, hist_img = visualize_outputs_with_matplotlib(norm_gray, masks)
        
        # Compute statistics
        stats = compute_statistics(masks, norm_gray)
        logger.info(f"Statistics: {stats}")

        # Convert images to base64
        result = {
            "normalized_image": image_to_base64(norm_img),
            "segmentation_mask": image_to_base64(mask_img),
            "intensity_histogram": image_to_base64(hist_img),
            "statistics": stats
        }
        
        logger.info("✅ Prediction complete")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error in predict_fn: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

def output_fn(prediction, accept='application/json'):
    """
    Serialize the prediction result.
    """
    logger.info(f"Formatting output with accept type: {accept}")
    
    if accept == 'application/json' or accept is None:
        return json.dumps(prediction), accept
    else:
        raise ValueError(f"Unsupported accept type: {accept}")