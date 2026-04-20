"""
Local testing script for SageMaker inference handler
Tests the inference code locally before deploying to SageMaker
"""

import os
import sys
import json
import base64
import argparse
import logging
from pathlib import Path

# Add current directory to path to import inference module
# The inference code is in sagemaker_async_inference.py
sys.path.insert(0, os.path.dirname(__file__))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_inference_handler(image_path, diameter=None, denoise=False, blur=False, output_dir='local_test_results'):
    """
    Test the SageMaker inference handler locally
    
    Args:
        image_path: Path to input image
        diameter: Cell diameter parameter
        denoise: Whether to apply denoising
        blur: Whether to apply Gaussian blur
        output_dir: Directory to save results
    """
    try:
        # Import the inference handler
        from sagemaker_async_inference import model_fn, input_fn, predict_fn, output_fn
        
        logger.info("=" * 60)
        logger.info("Local Inference Test")
        logger.info("=" * 60)
        
        # Step 1: Load model (model_fn)
        logger.info("\n📦 Step 1: Loading model...")
        model_dir = os.path.join(os.path.dirname(__file__), 'model_artifact')
        os.makedirs(model_dir, exist_ok=True)
        
        try:
            model = model_fn(model_dir)
            logger.info("✅ Model loaded successfully")
        except Exception as e:
            logger.error(f"❌ Model loading failed: {e}")
            logger.info("\n💡 Note: Model loading will download Cellpose weights on first run")
            logger.info("   This may take a few minutes...")
            raise
        
        # Step 2: Prepare input (input_fn)
        logger.info("\n📥 Step 2: Preparing input...")
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        payload = {
            'image': image_b64,
            'diameter': diameter,
            'denoise': denoise,
            'blur': blur
        }
        
        request_body = json.dumps(payload)
        input_data = input_fn(request_body, 'application/json')
        logger.info("✅ Input prepared successfully")
        logger.info(f"   Image: {image_path}")
        logger.info(f"   Parameters: diameter={diameter}, denoise={denoise}, blur={blur}")
        
        # Step 3: Run prediction (predict_fn)
        logger.info("\n🔮 Step 3: Running prediction...")
        prediction = predict_fn(input_data, model)
        logger.info("✅ Prediction completed successfully")
        
        # Step 4: Format output (output_fn)
        logger.info("\n📤 Step 4: Formatting output...")
        output, content_type = output_fn(prediction, 'application/json')
        logger.info("✅ Output formatted successfully")
        
        # Step 5: Save results
        logger.info("\n💾 Step 5: Saving results...")
        os.makedirs(output_dir, exist_ok=True)
        
        # Parse output
        results = json.loads(output)
        
        # Save statistics
        stats = results.get('statistics', {})
        stats_path = os.path.join(output_dir, 'statistics.json')
        with open(stats_path, 'w') as f:
            json.dump(stats, f, indent=2)
        logger.info(f"   Saved: {stats_path}")
        
        # Save images
        for img_name in ['normalized_image', 'segmentation_mask', 'intensity_histogram']:
            if img_name in results:
                img_data = base64.b64decode(results[img_name])
                img_path = os.path.join(output_dir, f'{img_name}.png')
                with open(img_path, 'wb') as f:
                    f.write(img_data)
                logger.info(f"   Saved: {img_path}")
        
        # Print statistics
        logger.info("\n" + "=" * 60)
        logger.info("Results Summary")
        logger.info("=" * 60)
        logger.info(f"Cell Count: {stats.get('cell_count', 'N/A')}")
        logger.info(f"Confluency: {stats.get('confluency', 'N/A'):.2f}%")
        logger.info(f"Min Intensity: {stats.get('min_intensity', 'N/A')}")
        logger.info(f"Max Intensity: {stats.get('max_intensity', 'N/A')}")
        logger.info(f"\n✅ All results saved to: {output_dir}/")
        logger.info("=" * 60)
        
        return results
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.info("\n💡 Make sure you have installed all dependencies:")
        logger.info("   pip install -r requirements-sagemaker.txt")
        raise
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        raise

def main():
    parser = argparse.ArgumentParser(
        description="Test SageMaker inference handler locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic test
  python test_local_inference.py image.jpg
  
  # With custom parameters
  python test_local_inference.py image.jpg --diameter 30 --denoise --blur
  
  # Custom output directory
  python test_local_inference.py image.jpg --output-dir my_results
        """
    )
    
    parser.add_argument('image_path', type=str, help='Path to input image file')
    parser.add_argument('--diameter', type=float, default=None, 
                       help='Approximate cell diameter (default: auto-detect)')
    parser.add_argument('--denoise', action='store_true', 
                       help='Apply denoising preprocessing')
    parser.add_argument('--blur', action='store_true', 
                       help='Apply Gaussian blur preprocessing')
    parser.add_argument('--output-dir', type=str, default='local_test_results',
                       help='Directory to save results (default: local_test_results)')
    
    args = parser.parse_args()
    
    # Validate image path
    if not os.path.exists(args.image_path):
        logger.error(f"❌ Image file not found: {args.image_path}")
        sys.exit(1)
    
    # Run test
    try:
        test_inference_handler(
            args.image_path,
            diameter=args.diameter,
            denoise=args.denoise,
            blur=args.blur,
            output_dir=args.output_dir
        )
    except KeyboardInterrupt:
        logger.info("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
