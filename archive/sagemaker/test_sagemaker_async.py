"""
Client script to test SageMaker Asynchronous Inference endpoint
"""

import boto3
import json
import base64
import time
from pathlib import Path

# Configuration
ENDPOINT_NAME = "fibroblast-detection-endpoint"
REGION = "us-east-1"
INPUT_BUCKET = "your-sagemaker-bucket"
OUTPUT_BUCKET = "your-sagemaker-bucket"

def encode_image(image_path):
    """Encode image file to base64"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

def invoke_async_endpoint(image_path, diameter=30, denoise=False, blur=False):
    """
    Invoke SageMaker async endpoint with an image
    
    Args:
        image_path: Path to image file
        diameter: Approximate cell diameter
        denoise: Whether to apply denoising
        blur: Whether to apply Gaussian blur
    
    Returns:
        Output location S3 path
    """
    s3 = boto3.client('s3', region_name=REGION)
    sagemaker_runtime = boto3.client('sagemaker-runtime', region_name=REGION)
    
    # Prepare payload
    image_b64 = encode_image(image_path)
    payload = {
        'image': image_b64,
        'diameter': diameter,
        'denoise': denoise,
        'blur': blur
    }
    
    # Upload input to S3
    input_key = f"async-inference/input/request_{int(time.time())}.json"
    s3.put_object(
        Bucket=INPUT_BUCKET,
        Key=input_key,
        Body=json.dumps(payload),
        ContentType='application/json'
    )
    
    input_location = f"s3://{INPUT_BUCKET}/{input_key}"
    print(f"Input uploaded to: {input_location}")
    
    # Invoke async endpoint
    print(f"Invoking endpoint: {ENDPOINT_NAME}...")
    response = sagemaker_runtime.invoke_endpoint_async(
        EndpointName=ENDPOINT_NAME,
        InputLocation=input_location,
        ContentType='application/json'
    )
    
    output_location = response['OutputLocation']
    print(f"Async inference started. Output will be at: {output_location}")
    
    return output_location

def poll_for_results(output_location, max_wait_time=600, poll_interval=5):
    """
    Poll S3 for results
    
    Args:
        output_location: S3 path to output
        max_wait_time: Maximum time to wait (seconds)
        poll_interval: Time between polls (seconds)
    
    Returns:
        Results dictionary or None if timeout
    """
    s3 = boto3.client('s3', region_name=REGION)
    
    # Parse S3 path
    # Format: s3://bucket/key
    parts = output_location.replace('s3://', '').split('/', 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ''
    
    print(f"Polling for results at s3://{bucket}/{key}...")
    
    start_time = time.time()
    while time.time() - start_time < max_wait_time:
        try:
            response = s3.get_object(Bucket=bucket, Key=key)
            results = json.loads(response['Body'].read())
            print("Results received!")
            return results
        except s3.exceptions.NoSuchKey:
            elapsed = time.time() - start_time
            print(f"Waiting for results... ({elapsed:.0f}s elapsed)")
            time.sleep(poll_interval)
        except Exception as e:
            print(f"Error polling: {e}")
            time.sleep(poll_interval)
    
    print(f"Timeout after {max_wait_time} seconds")
    return None

def save_results(results, output_dir='results'):
    """Save results (images and statistics) to local directory"""
    Path(output_dir).mkdir(exist_ok=True)
    
    # Save statistics
    stats = results.get('statistics', {})
    with open(f"{output_dir}/statistics.json", 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"\nStatistics:")
    print(f"  Cell Count: {stats.get('cell_count', 'N/A')}")
    print(f"  Confluency: {stats.get('confluency', 'N/A'):.2f}%")
    print(f"  Min Intensity: {stats.get('min_intensity', 'N/A')}")
    print(f"  Max Intensity: {stats.get('max_intensity', 'N/A')}")
    
    # Decode and save images
    for img_name, img_b64 in [
        ('normalized_image', results.get('normalized_image')),
        ('segmentation_mask', results.get('segmentation_mask')),
        ('intensity_histogram', results.get('intensity_histogram'))
    ]:
        if img_b64:
            img_data = base64.b64decode(img_b64)
            output_path = f"{output_dir}/{img_name}.png"
            with open(output_path, 'wb') as f:
                f.write(img_data)
            print(f"  Saved: {output_path}")

def main():
    """Main function to test async endpoint"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test SageMaker Async Inference endpoint")
    parser.add_argument('image_path', type=str, help='Path to input image')
    parser.add_argument('--diameter', type=float, default=30, help='Cell diameter')
    parser.add_argument('--denoise', action='store_true', help='Apply denoising')
    parser.add_argument('--blur', action='store_true', help='Apply Gaussian blur')
    parser.add_argument('--output-dir', type=str, default='results', help='Output directory')
    
    args = parser.parse_args()
    
    # Invoke endpoint
    output_location = invoke_async_endpoint(
        args.image_path,
        diameter=args.diameter,
        denoise=args.denoise,
        blur=args.blur
    )
    
    # Poll for results
    results = poll_for_results(output_location)
    
    if results:
        # Save results
        save_results(results, args.output_dir)
        print(f"\n✅ Success! Results saved to {args.output_dir}/")
    else:
        print("\n❌ Failed to get results")

if __name__ == "__main__":
    main()
