# Pay-Per-Use Deployment Options for Fibroblast Detection

This guide explains how to deploy your Cellpose-based fibroblast detection model with **pay-per-inference** pricing instead of paying for a persistent endpoint that runs 24/7.

## Cost Comparison

| Deployment Type | Hardware | Hourly Cost | Idle Cost | Best For |
|----------------|----------|-------------|-----------|----------|
| **Persistent GPU Endpoint** | ml.g4dn.xlarge (GPU) | ~$0.736/hour | ~$0.736/hour | High-volume, low-latency needs |
| **Serverless (CPU)** | 6GB RAM (CPU) | ~$0.000012/sec | $0 | Low-volume, CPU-acceptable |
| **Batch Transform (GPU)** | ml.g4dn.xlarge (GPU) | ~$0.736/hour | $0 | Batch processing, scheduled jobs |
| **On-Demand Endpoint** | ml.g4dn.xlarge (GPU) | ~$0.736/hour | $0* | Real-time, infrequent use |

*Requires custom auto-shutdown/startup logic

---

## Option 1: SageMaker Serverless Inference ⭐ (EASIEST)

**Best for:** Low-to-medium volume inference with acceptable CPU performance

### ✅ Pros
- **True pay-per-use**: Only pay for actual inference compute time (~$0.000012/second)
- **$0 when idle**: No cost when not processing requests
- **Auto-scaling**: Automatically scales from 0 to many instances
- **No infrastructure management**: Fully managed by AWS
- **Built-in load balancing**: Handles concurrent requests automatically

### ❌ Cons
- **CPU only (NO GPU)**: Cellpose will be slower on CPU
- **Max payload**: 4MB limit (may need to compress/resize images)
- **Max inference time**: 60 seconds per request
- **Cold start**: First request after idle has 10-60s delay

### Usage

```bash
# Deploy as serverless endpoint
python sagemaker_deploy.py --serverless --image-uri YOUR_ECR_IMAGE_URI

# Or if you already have the image pushed:
python sagemaker_deploy.py --skip-ecr --serverless --image-uri YOUR_ECR_IMAGE_URI
```

### Pricing Example
- 1000 images/day @ 10 seconds each = 10,000 seconds
- Cost: 10,000 × $0.000012 = **$0.12/day** or **$3.60/month**
- vs. Persistent GPU: $0.736 × 24 × 30 = **$530/month**

---

## Option 2: SageMaker Batch Transform (WITH GPU) ⭐ (RECOMMENDED FOR BATCH)

**Best for:** Processing batches of images on a schedule or as needed

### ✅ Pros
- **GPU support**: Full Cellpose performance with CUDA
- **Pay only when running**: Instances spin up for the job, then terminate
- **Batch optimized**: Efficient for processing many images at once
- **S3 integration**: Read from and write to S3 automatically
- **No endpoint management**: No persistent endpoint to maintain

### ❌ Cons
- **Not real-time**: Batch jobs, not API endpoints
- **Startup time**: Takes 5-10 minutes to provision GPU instance
- **Minimum job time**: Billed for at least 1 hour per job

### Implementation

Create a new file `sagemaker_batch_deploy.py`:

```python
import boto3
import sagemaker
from sagemaker.model import Model
from datetime import datetime

ROLE = "arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/SageMakerFibroblastRole"
REGION = "us-east-2"
BUCKET_NAME = "YOUR_S3_BUCKET"
MODEL_NAME = "fibroblast-detection-model"

sess = sagemaker.Session()
sagemaker_client = boto3.client('sagemaker', region_name=REGION)

def create_batch_transform_job(
    image_uri,
    model_uri,
    input_s3_uri,
    output_s3_uri,
    instance_type="ml.g4dn.xlarge",
    instance_count=1
):
    """
    Create a batch transform job for processing images

    Args:
        image_uri: ECR URI of Docker image
        model_uri: S3 URI of model artifact
        input_s3_uri: S3 path with input images (e.g., s3://bucket/input/)
        output_s3_uri: S3 path for results (e.g., s3://bucket/output/)
        instance_type: GPU instance type
        instance_count: Number of instances
    """

    # Create or update model
    print(f"Creating model: {MODEL_NAME}")
    try:
        sagemaker_client.create_model(
            ModelName=MODEL_NAME,
            PrimaryContainer={
                'Image': image_uri,
                'ModelDataUrl': model_uri,
                'Environment': {
                    'SAGEMAKER_MODEL_SERVER_WORKERS': '1',
                    'SAGEMAKER_MODEL_SERVER_TIMEOUT': '600'
                }
            },
            ExecutionRoleArn=ROLE
        )
        print(f"✅ Model created: {MODEL_NAME}")
    except sagemaker_client.exceptions.ResourceInUse:
        print(f"ℹ️  Model already exists: {MODEL_NAME}")

    # Create batch transform job
    job_name = f"fibroblast-batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    print(f"\nCreating batch transform job: {job_name}")
    print(f"Input: {input_s3_uri}")
    print(f"Output: {output_s3_uri}")
    print(f"Instance: {instance_type} (GPU)")

    sagemaker_client.create_transform_job(
        TransformJobName=job_name,
        ModelName=MODEL_NAME,
        BatchStrategy='SingleRecord',  # Process one image at a time
        TransformInput={
            'DataSource': {
                'S3DataSource': {
                    'S3DataType': 'S3Prefix',
                    'S3Uri': input_s3_uri
                }
            },
            'ContentType': 'application/json',
            'SplitType': 'Line'
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
    print(f"💰 Cost: ~$0.736/hour (only while job is running)")
    print(f"\nMonitor job:")
    print(f"  aws sagemaker describe-transform-job --transform-job-name {job_name}")

    return job_name

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run batch transform for Fibroblast Detection")
    parser.add_argument('--image-uri', type=str, required=True,
                       help='ECR image URI')
    parser.add_argument('--model-uri', type=str, required=True,
                       help='S3 URI of model artifact')
    parser.add_argument('--input', type=str, required=True,
                       help='S3 path with input images')
    parser.add_argument('--output', type=str, required=True,
                       help='S3 path for output results')
    parser.add_argument('--instance-type', type=str, default='ml.g4dn.xlarge',
                       help='Instance type (default: ml.g4dn.xlarge)')
    parser.add_argument('--instance-count', type=int, default=1,
                       help='Number of instances (default: 1)')

    args = parser.parse_args()

    job_name = create_batch_transform_job(
        image_uri=args.image_uri,
        model_uri=args.model_uri,
        input_s3_uri=args.input,
        output_s3_uri=args.output,
        instance_type=args.instance_type,
        instance_count=args.instance_count
    )

    print(f"\n✅ Job submitted: {job_name}")
    print("Instance will auto-terminate when job completes.")
```

### Usage

```bash
# 1. Upload input images to S3
aws s3 sync ./input_images/ s3://YOUR_S3_BUCKET/batch-input/

# 2. Run batch transform job
python sagemaker_batch_deploy.py \
  --image-uri YOUR_ECR_IMAGE_URI \
  --model-uri s3://YOUR_S3_BUCKET/models/fibroblast-detection-model/model.tar.gz \
  --input s3://YOUR_S3_BUCKET/batch-input/ \
  --output s3://YOUR_S3_BUCKET/batch-output/

# 3. Download results when complete
aws s3 sync s3://YOUR_S3_BUCKET/batch-output/ ./results/
```

### Pricing Example
- Process 500 images once per week
- Job takes 1 hour with GPU
- Cost: 1 hour × $0.736 × 4 weeks = **$2.94/month**
- vs. Persistent GPU: **$530/month**

---

## Option 3: On-Demand Endpoint with Auto-Shutdown

**Best for:** Real-time inference with infrequent usage patterns

### Implementation Strategy

Create endpoints on-demand and automatically delete them after a period of inactivity using:

1. **CloudWatch + Lambda**: Monitor endpoint metrics and delete after N minutes of inactivity
2. **API Gateway + Lambda**: Create endpoint on first request, delete after timeout
3. **Manual scripts**: Start endpoint when needed, stop when done

### Example Auto-Shutdown Script

```python
import boto3
import time
from datetime import datetime, timedelta

sagemaker_client = boto3.client('sagemaker', region_name='us-east-2')
cloudwatch = boto3.client('cloudwatch', region_name='us-east-2')

def check_endpoint_activity(endpoint_name, minutes=15):
    """Check if endpoint has had any invocations in the last N minutes"""

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=minutes)

    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/SageMaker',
        MetricName='Invocations',
        Dimensions=[
            {'Name': 'EndpointName', 'Value': endpoint_name},
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=60,
        Statistics=['Sum']
    )

    total_invocations = sum([point['Sum'] for point in response['Datapoints']])
    return total_invocations > 0

def auto_shutdown_endpoint(endpoint_name, idle_minutes=15):
    """Delete endpoint if idle for specified minutes"""

    if not check_endpoint_activity(endpoint_name, idle_minutes):
        print(f"Endpoint {endpoint_name} idle for {idle_minutes} minutes. Deleting...")
        sagemaker_client.delete_endpoint(EndpointName=endpoint_name)
        print(f"✅ Endpoint deleted")
        return True
    else:
        print(f"Endpoint {endpoint_name} is active. Keeping alive.")
        return False

# Run this in a cron job or Lambda function
if __name__ == "__main__":
    auto_shutdown_endpoint("fibroblast-detection-endpoint", idle_minutes=30)
```

---

## Recommendation by Use Case

### 🎯 **Low volume, infrequent (< 100 images/day)**
→ **Serverless (CPU)** - $0.12/day
- Trade slower CPU inference for zero idle costs

### 🎯 **Batch processing (weekly/daily batches)**
→ **Batch Transform (GPU)** - $2.94/month for weekly jobs
- Full GPU performance, pay only when running

### 🎯 **Medium volume real-time (100-1000 images/day)**
→ **Serverless (CPU)** or **On-Demand with Auto-Shutdown**
- Serverless: ~$1.20/day
- On-Demand: $0.736/hour × hours running

### 🎯 **High volume 24/7 (> 5000 images/day)**
→ **Persistent GPU Endpoint**
- At high volume, persistent endpoint becomes cost-effective

---

## Quick Start

### Option 1: Serverless (CPU)
```bash
python sagemaker_deploy.py --serverless --image-uri YOUR_ECR_IMAGE_URI
```

### Option 2: Batch Transform (GPU)
```bash
# Create the batch script first
cat > sagemaker_batch_deploy.py << 'EOF'
[Copy the batch transform code from above]
EOF

# Run batch job
python sagemaker_batch_deploy.py \
  --image-uri YOUR_ECR_IMAGE_URI \
  --model-uri s3://BUCKET/models/model.tar.gz \
  --input s3://BUCKET/batch-input/ \
  --output s3://BUCKET/batch-output/
```

---

## Cost Monitoring

Set up billing alerts:
```bash
# Create CloudWatch billing alarm
aws cloudwatch put-metric-alarm \
  --alarm-name sagemaker-cost-alert \
  --alarm-description "Alert when SageMaker costs exceed $50/month" \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --period 86400 \
  --evaluation-periods 1 \
  --threshold 50 \
  --comparison-operator GreaterThanThreshold
```

---

## Questions?

- **Need GPU + pay-per-use?** → Batch Transform
- **Need real-time + pay-per-use?** → Serverless (CPU only)
- **Processing large batches weekly?** → Batch Transform
- **Low volume API?** → Serverless

Choose based on your specific usage pattern!
