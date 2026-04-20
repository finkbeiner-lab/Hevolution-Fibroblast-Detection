#!/usr/bin/env python3
"""
Clean up failed SageMaker endpoint
"""

import boto3
import sys

ENDPOINT_NAME = "fibroblast-detection-endpoint"
REGION = "us-east-2"

def cleanup_endpoint():
    """Delete the failed endpoint and its configuration"""
    import time
    sagemaker_client = boto3.client('sagemaker', region_name=REGION)
    
    # Step 1: Delete endpoint first (if it exists)
    try:
        response = sagemaker_client.describe_endpoint(EndpointName=ENDPOINT_NAME)
        status = response['EndpointStatus']
        print(f"Endpoint status: {status}")
        
        print(f"\nDeleting endpoint...")
        sagemaker_client.delete_endpoint(EndpointName=ENDPOINT_NAME)
        print(f"✅ Endpoint deletion initiated: {ENDPOINT_NAME}")
        
        # Wait a bit for endpoint deletion to start
        print("⏳ Waiting 10 seconds for endpoint deletion to process...")
        time.sleep(10)
        
    except sagemaker_client.exceptions.ResourceNotFound:
        print(f"ℹ️  Endpoint '{ENDPOINT_NAME}' not found (already deleted)")
    except Exception as e:
        print(f"⚠️  Error deleting endpoint: {e}")
    
    # Step 2: Delete endpoint config (can only be deleted after endpoint is gone)
    config_name = ENDPOINT_NAME
    max_retries = 6
    for i in range(max_retries):
        try:
            sagemaker_client.delete_endpoint_config(EndpointConfigName=config_name)
            print(f"✅ Endpoint config deleted: {config_name}")
            break
        except sagemaker_client.exceptions.ResourceNotFound:
            print(f"ℹ️  Endpoint config '{config_name}' not found (already deleted)")
            break
        except Exception as e:
            if "Cannot delete" in str(e) or "in use" in str(e).lower():
                if i < max_retries - 1:
                    wait_time = 10 * (i + 1)
                    print(f"⚠️  Endpoint config still in use, waiting {wait_time}s... (attempt {i+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"❌ Could not delete endpoint config after {max_retries} attempts")
                    print("   You may need to wait longer or delete manually in AWS Console")
            else:
                print(f"⚠️  Error deleting endpoint config: {e}")
                break
    
    print("\n✅ Cleanup complete!")
    print("   You can now run the deployment script")

if __name__ == "__main__":
    print("=" * 60)
    print("Cleaning up failed SageMaker endpoint")
    print("=" * 60)
    cleanup_endpoint()
