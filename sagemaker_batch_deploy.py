"""
SageMaker Batch Transform for Fibroblast Detection

This script enables PAY-PER-USE inference with GPU support.
Instances spin up for the batch job, then automatically terminate.

Perfect for:
- Processing batches of images weekly/daily
- Full GPU performance
- $0 cost when not running
"""

import boto3
import sagemaker
from sagemaker.model import Model
from datetime import datetime
import os
import json

# Configuration
ROLE = "arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/SageMakerFibroblastRole"
REGION = "us-east-2"
BUCKET_NAME = "YOUR_S3_BUCKET"
MODEL_NAME = "fibroblast-detection-batch-model"
AWS_PROFILE = os.environ.get("AWS_PROFILE", "admin")

sess = sagemaker.Session()
sagemaker_client = boto3.client('sagemaker', region_name=REGION)
s3_client = boto3.client('s3', region_name=REGION)


def prepare_batch_input(local_image_dir, s3_input_prefix):
    """
    Upload images to S3 and create manifest file for batch processing

    Args:
        local_image_dir: Local directory containing images
        s3_input_prefix: S3 prefix for input data (e.g., 's3://bucket/batch-input/')
    """
    import os
    from pathlib import Path

    print(f"📦 Preparing batch input from {local_image_dir}")

    if not os.path.exists(local_image_dir):
        raise ValueError(f"Directory not found: {local_image_dir}")

    # Find all image files
    image_extensions = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
    image_files = [
        f for f in Path(local_image_dir).rglob('*')
        if f.is_file() and f.suffix.lower() in image_extensions
    ]

    if not image_files:
        raise ValueError(f"No image files found in {local_image_dir}")

    print(f"Found {len(image_files)} images")

    # Upload images to S3
    s3_uri = s3_input_prefix.rstrip('/')
    bucket = s3_uri.replace('s3://', '').split('/')[0]
    prefix = '/'.join(s3_uri.replace('s3://', '').split('/')[1:])

    print(f"\n📤 Uploading to S3: {s3_uri}/")

    for img_path in image_files:
        s3_key = f"{prefix}/{img_path.name}"
        print(f"  Uploading {img_path.name}...")
        s3_client.upload_file(str(img_path), bucket, s3_key)

    print(f"✅ Uploaded {len(image_files)} images to {s3_uri}/")
    return s3_uri + '/'


def create_or_update_model(image_uri, model_uri):
    """
    Create or update the SageMaker model

    Args:
        image_uri: ECR URI of Docker image
        model_uri: S3 URI of model artifact
    """
    print(f"\n📋 Creating/updating model: {MODEL_NAME}")

    # Delete existing model if it exists
    try:
        sagemaker_client.describe_model(ModelName=MODEL_NAME)
        print(f"  Deleting existing model...")
        sagemaker_client.delete_model(ModelName=MODEL_NAME)
        print(f"  ✅ Existing model deleted")
    except sagemaker_client.exceptions.ResourceNotFound:
        pass

    # Create new model
    try:
        sagemaker_client.create_model(
            ModelName=MODEL_NAME,
            PrimaryContainer={
                'Image': image_uri,
                'ModelDataUrl': model_uri,
                'Environment': {
                    'SAGEMAKER_MODEL_SERVER_WORKERS': '1',
                    'SAGEMAKER_MODEL_SERVER_TIMEOUT': '600',
                    'SAGEMAKER_PROGRAM': 'inference.py'
                }
            },
            ExecutionRoleArn=ROLE
        )
        print(f"✅ Model created: {MODEL_NAME}")
        return True
    except Exception as e:
        print(f"❌ Error creating model: {e}")
        raise


def create_batch_transform_job(
    image_uri,
    model_uri,
    input_s3_uri,
    output_s3_uri,
    instance_type="ml.g4dn.xlarge",
    instance_count=1,
    max_payload_mb=6,
    strategy="SingleRecord"
):
    """
    Create a batch transform job for processing images

    Args:
        image_uri: ECR URI of Docker image
        model_uri: S3 URI of model artifact
        input_s3_uri: S3 path with input images (e.g., s3://bucket/input/)
        output_s3_uri: S3 path for results (e.g., s3://bucket/output/)
        instance_type: GPU instance type (default: ml.g4dn.xlarge)
        instance_count: Number of instances (default: 1)
        max_payload_mb: Max payload size in MB (default: 6)
        strategy: Batch strategy - SingleRecord or MultiRecord
    """

    # Create or update model
    create_or_update_model(image_uri, model_uri)

    # Create batch transform job
    job_name = f"fibroblast-batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print("\n" + "=" * 60)
    print(f"🚀 Creating Batch Transform Job")
    print("=" * 60)
    print(f"Job Name: {job_name}")
    print(f"Input:    {input_s3_uri}")
    print(f"Output:   {output_s3_uri}")
    print(f"Instance: {instance_type} (GPU)")
    print(f"Count:    {instance_count}")
    print(f"Strategy: {strategy}")
    print("=" * 60)

    try:
        sagemaker_client.create_transform_job(
            TransformJobName=job_name,
            ModelName=MODEL_NAME,
            BatchStrategy=strategy,
            MaxPayloadInMB=max_payload_mb,
            TransformInput={
                'DataSource': {
                    'S3DataSource': {
                        'S3DataType': 'S3Prefix',
                        'S3Uri': input_s3_uri
                    }
                },
                'ContentType': 'application/json',
                'SplitType': 'None'  # Process entire file
            },
            TransformOutput={
                'S3OutputPath': output_s3_uri,
                'Accept': 'application/json',
                'AssembleWith': 'Line'
            },
            TransformResources={
                'InstanceType': instance_type,
                'InstanceCount': instance_count
            }
        )

        print(f"\n✅ Batch transform job created: {job_name}")
        print(f"\n💰 COST ESTIMATE:")
        print(f"   Instance will run until all images are processed")
        print(f"   Cost: ~$0.736/hour for ml.g4dn.xlarge (billed per second)")
        print(f"   Instance auto-terminates when job completes")
        print(f"\n📊 Monitor job status:")
        print(f"   aws sagemaker describe-transform-job --transform-job-name {job_name} --region {REGION}")
        print(f"\n   Or in AWS Console:")
        print(f"   SageMaker → Inference → Batch transform jobs → {job_name}")

        # Wait for job to complete (optional)
        print(f"\n⏳ Waiting for job to complete (this may take a while)...")
        print(f"   You can press Ctrl+C to stop waiting (job will continue running)")

        try:
            waiter = sagemaker_client.get_waiter('transform_job_completed_or_stopped')
            waiter.wait(TransformJobName=job_name)

            # Check final status
            response = sagemaker_client.describe_transform_job(TransformJobName=job_name)
            status = response['TransformJobStatus']

            if status == 'Completed':
                print(f"\n✅ Job completed successfully!")
                print(f"\n📥 Download results:")
                print(f"   aws s3 sync {output_s3_uri} ./results/ --region {REGION}")
            elif status == 'Failed':
                print(f"\n❌ Job failed!")
                print(f"   Failure reason: {response.get('FailureReason', 'Unknown')}")
            else:
                print(f"\n⚠️  Job stopped with status: {status}")

        except KeyboardInterrupt:
            print(f"\n⚠️  Stopped waiting, but job is still running in background")
            print(f"   Check status with: aws sagemaker describe-transform-job --transform-job-name {job_name}")

        return job_name

    except Exception as e:
        print(f"\n❌ Error creating batch transform job: {e}")
        raise


def monitor_job(job_name):
    """
    Monitor the status of a batch transform job

    Args:
        job_name: Name of the transform job
    """
    print(f"📊 Monitoring job: {job_name}")

    while True:
        try:
            response = sagemaker_client.describe_transform_job(TransformJobName=job_name)
            status = response['TransformJobStatus']

            print(f"\rStatus: {status}", end='', flush=True)

            if status in ['Completed', 'Failed', 'Stopped']:
                print(f"\n\n✅ Final status: {status}")

                if status == 'Failed':
                    print(f"Failure reason: {response.get('FailureReason', 'Unknown')}")

                break

            import time
            time.sleep(30)  # Check every 30 seconds

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Stopped monitoring (job still running)")
            break
        except Exception as e:
            print(f"\n❌ Error monitoring job: {e}")
            break


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run SageMaker Batch Transform for Fibroblast Detection (GPU, Pay-per-use)"
    )

    # Required arguments
    parser.add_argument('--image-uri', type=str, required=True,
                       help='ECR image URI (from sagemaker_deploy.py --setup-ecr-only)')
    parser.add_argument('--model-uri', type=str, required=True,
                       help='S3 URI of model artifact (from sagemaker_deploy.py)')

    # Input/output
    parser.add_argument('--input-s3', type=str, default=None,
                       help='S3 path with input images (e.g., s3://bucket/input/)')
    parser.add_argument('--input-dir', type=str, default=None,
                       help='Local directory with images (will upload to S3)')
    parser.add_argument('--output-s3', type=str,
                       default=f's3://{BUCKET_NAME}/batch-output/',
                       help='S3 path for output results')

    # Instance configuration
    parser.add_argument('--instance-type', type=str, default='ml.g4dn.xlarge',
                       help='Instance type (default: ml.g4dn.xlarge - smallest GPU)')
    parser.add_argument('--instance-count', type=int, default=1,
                       help='Number of instances (default: 1)')

    # Job options
    parser.add_argument('--monitor', action='store_true',
                       help='Monitor job status until completion')
    parser.add_argument('--job-name', type=str, default=None,
                       help='Monitor existing job by name')

    args = parser.parse_args()

    # Monitor existing job
    if args.job_name:
        monitor_job(args.job_name)
        exit(0)

    # Prepare input
    input_s3_uri = args.input_s3
    if args.input_dir:
        if not input_s3_uri:
            input_s3_uri = f's3://{BUCKET_NAME}/batch-input/'
        input_s3_uri = prepare_batch_input(args.input_dir, input_s3_uri)
    elif not input_s3_uri:
        print("❌ Error: Must provide either --input-s3 or --input-dir")
        exit(1)

    # Create batch transform job
    job_name = create_batch_transform_job(
        image_uri=args.image_uri,
        model_uri=args.model_uri,
        input_s3_uri=input_s3_uri,
        output_s3_uri=args.output_s3,
        instance_type=args.instance_type,
        instance_count=args.instance_count
    )

    print(f"\n✅ Batch job submitted: {job_name}")
    print("💰 Instance will auto-terminate when job completes (pay only while running)")

    if args.monitor:
        monitor_job(job_name)
