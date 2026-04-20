#!/usr/bin/env python3
"""
Test script for Gradio-SageMaker.py
Tests the SageMaker endpoint connection and async inference workflow
"""

import os
import sys
import boto3
import json
import base64
import time
from PIL import Image
import io

# Configuration
ENDPOINT_NAME = os.getenv("SAGEMAKER_ENDPOINT_NAME", "fibroblast-detection-endpoint")
REGION = os.getenv("AWS_REGION", "us-east-2")
BUCKET_NAME = os.getenv("S3_BUCKET", "YOUR_S3_BUCKET")

# Initialize AWS clients
s3_client = boto3.client('s3', region_name=REGION)
sagemaker_runtime = boto3.client('sagemaker-runtime', region_name=REGION)

def test_endpoint_status():
    """Test if endpoint exists and is in service"""
    print("=" * 60)
    print("Test 1: Checking SageMaker Endpoint Status")
    print("=" * 60)
    
    try:
        sagemaker = boto3.client('sagemaker', region_name=REGION)
        response = sagemaker.describe_endpoint(EndpointName=ENDPOINT_NAME)
        status = response['EndpointStatus']
        
        print(f"✅ Endpoint found: {ENDPOINT_NAME}")
        print(f"   Status: {status}")
        print(f"   Region: {REGION}")
        
        if status == "InService":
            print("   ✅ Endpoint is ready for inference!")
            return True
        else:
            print(f"   ⚠️  Endpoint is not ready (status: {status})")
            print("   Wait for endpoint to be InService before testing")
            return False
            
    except Exception as e:
        print(f"❌ Error checking endpoint: {e}")
        return False

def test_s3_access():
    """Test S3 bucket access"""
    print("\n" + "=" * 60)
    print("Test 2: Checking S3 Bucket Access")
    print("=" * 60)
    
    try:
        # Test list access
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, MaxKeys=1)
        print(f"✅ S3 bucket accessible: {BUCKET_NAME}")
        print(f"   Region: {REGION}")
        return True
    except s3_client.exceptions.NoSuchBucket:
        print(f"❌ Bucket does not exist: {BUCKET_NAME}")
        print(f"   Create it with: aws s3 mb s3://{BUCKET_NAME} --region {REGION}")
        return False
    except Exception as e:
        print(f"❌ Error accessing S3: {e}")
        print("   Check IAM permissions for S3 access")
        return False

def test_async_inference(image_path):
    """Test async inference with a sample image"""
    print("\n" + "=" * 60)
    print("Test 3: Testing Async Inference")
    print("=" * 60)
    
    if not os.path.exists(image_path):
        print(f"❌ Image file not found: {image_path}")
        return False
    
    try:
        # Load and encode image
        print(f"📷 Loading image: {image_path}")
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        image_size = len(image_bytes) / (1024 * 1024)  # MB
        print(f"   Image size: {image_size:.2f} MB")
        print(f"   Base64 length: {len(image_b64)} characters")
        
        # Prepare payload
        payload = {
            'image': image_b64,
            'diameter': 30,
            'denoise': False,
            'blur': False
        }
        
        # Upload to S3
        print("\n📤 Uploading input to S3...")
        input_key = f"async-inference/input/test_request_{int(time.time())}.json"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=input_key,
            Body=json.dumps(payload),
            ContentType='application/json'
        )
        input_location = f"s3://{BUCKET_NAME}/{input_key}"
        print(f"   ✅ Uploaded to: {input_location}")
        
        # Invoke endpoint
        print("\n🚀 Invoking SageMaker endpoint...")
        start_time = time.time()
        response = sagemaker_runtime.invoke_endpoint_async(
            EndpointName=ENDPOINT_NAME,
            InputLocation=input_location,
            ContentType='application/json'
        )
        
        output_location = response['OutputLocation']
        print(f"   ✅ Invocation successful!")
        print(f"   Output location: {output_location}")
        
        # Parse S3 path
        parts = output_location.replace('s3://', '').split('/', 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ''
        
        # Poll for results
        print("\n⏳ Polling for results (this may take 30-120 seconds)...")
        max_wait = 300  # 5 minutes
        poll_interval = 5
        elapsed = 0
        
        while elapsed < max_wait:
            try:
                result_obj = s3_client.get_object(Bucket=bucket, Key=key)
                results = json.loads(result_obj['Body'].read())
                
                total_time = int(time.time() - start_time)
                print(f"\n✅ Results received! (took {total_time} seconds)")
                
                # Display statistics
                stats = results.get('statistics', {})
                print("\n📊 Results:")
                print(f"   Cell Count: {stats.get('cell_count', 'N/A')}")
                print(f"   Confluency: {stats.get('confluency', 'N/A'):.2f}%")
                print(f"   Min Intensity: {stats.get('min_intensity', 'N/A')}")
                print(f"   Max Intensity: {stats.get('max_intensity', 'N/A')}")
                
                # Check if images are present
                if 'normalized_image' in results:
                    print("   ✅ Normalized image: Present")
                if 'segmentation_mask' in results:
                    print("   ✅ Segmentation mask: Present")
                if 'intensity_histogram' in results:
                    print("   ✅ Intensity histogram: Present")
                
                return True
                
            except s3_client.exceptions.NoSuchKey:
                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0:  # Print every 10 seconds
                    print(f"   Still processing... ({elapsed}s elapsed)")
                time.sleep(poll_interval)
            except Exception as e:
                print(f"\n❌ Error reading results: {e}")
                return False
        
        print(f"\n❌ Timeout: No results after {max_wait} seconds")
        return False
        
    except Exception as e:
        print(f"\n❌ Error during inference: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("SageMaker Endpoint Test Suite")
    print("=" * 60)
    print(f"Endpoint: {ENDPOINT_NAME}")
    print(f"Region: {REGION}")
    print(f"S3 Bucket: {BUCKET_NAME}")
    print()
    
    # Test 1: Endpoint status
    endpoint_ok = test_endpoint_status()
    if not endpoint_ok:
        print("\n❌ Endpoint is not ready. Fix this before continuing.")
        sys.exit(1)
    
    # Test 2: S3 access
    s3_ok = test_s3_access()
    if not s3_ok:
        print("\n❌ S3 access failed. Fix this before continuing.")
        sys.exit(1)
    
    # Test 3: Async inference (if image provided)
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        inference_ok = test_async_inference(image_path)
        if inference_ok:
            print("\n" + "=" * 60)
            print("✅ All tests passed!")
            print("=" * 60)
            print("\nYour Gradio app should work correctly.")
            print("Run: python Gradio-SageMaker.py")
        else:
            print("\n" + "=" * 60)
            print("❌ Inference test failed")
            print("=" * 60)
            print("\nCheck CloudWatch logs for endpoint errors:")
            print(f"   aws logs tail /aws/sagemaker/Endpoints/{ENDPOINT_NAME} --follow")
            sys.exit(1)
    else:
        print("\n" + "=" * 60)
        print("✅ Basic tests passed!")
        print("=" * 60)
        print("\nTo test inference, provide an image path:")
        print(f"   python {sys.argv[0]} path/to/image.jpg")
        print("\nOr test with Gradio:")
        print("   python Gradio-SageMaker.py")

if __name__ == "__main__":
    main()
