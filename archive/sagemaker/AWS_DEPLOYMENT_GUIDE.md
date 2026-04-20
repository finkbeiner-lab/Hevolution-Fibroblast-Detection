# AWS Deployment Guide - SageMaker Asynchronous Inference

Deploy your Fibroblast Detection application to AWS SageMaker Asynchronous Inference.

## Overview

Your application uses:
- **Cellpose** (requires GPU)
- **Gradio** (web UI)
- **OpenCV, NumPy, Matplotlib** (image processing)

**Why Asynchronous Inference?**
- ✅ Pay only for compute time used (no idle costs when scaled to zero)
- ✅ Handles long-running tasks (no timeout limits)
- ✅ GPU support (required for Cellpose)
- ✅ Auto-scales based on demand
- ✅ No infrastructure management

**Note:** SageMaker Serverless Inference does NOT support GPU instances, so we use Asynchronous Inference which provides similar cost benefits with GPU support.

---

## Prerequisites

### 1. AWS Setup
```bash
# Configure AWS CLI
aws configure

# Create S3 bucket
aws s3 mb s3://YOUR_S3_BUCKET --region us-east-2
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
pip install sagemaker boto3
```

### 3. Docker Setup
```bash
# Verify Docker is installed
docker --version

# Fix Docker permissions (if needed)
sudo usermod -aG docker $USER
newgrp docker  # or log out and back in
```

### 4. IAM Role
Ensure you have an IAM role with:
- `AmazonSageMakerFullAccess`
- `AmazonS3FullAccess`
- `AmazonEC2ContainerRegistryFullAccess`

**Current configuration in script:**
- **ROLE**: `arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/SageMakerFibroblastRole`
- **REGION**: `us-east-2`
- **BUCKET**: `YOUR_S3_BUCKET`

---

## Deployment Steps

### Step 1: Verify Configuration

The deployment script (`sagemaker_deploy.py`) is pre-configured. Verify if needed:
- IAM Role ARN
- Region
- S3 Bucket name

### Step 2: Deploy

Run the deployment script:

```bash
python sagemaker_deploy.py
```

**What the script does:**
1. ✅ Builds Docker image with all dependencies
2. ✅ Pushes image to ECR
3. ✅ Creates model artifact package
4. ✅ Uploads to S3
5. ✅ Deploys SageMaker Asynchronous Inference endpoint

**Script options:**
```bash
# Full deployment (recommended)
python sagemaker_deploy.py

# Skip ECR setup (if image already exists)
python sagemaker_deploy.py --skip-ecr --image-uri YOUR_ECR_URI

# Setup ECR only (test Docker separately)
python sagemaker_deploy.py --setup-ecr-only
```

### Step 3: Test the Endpoint

```bash
python test_sagemaker_async.py path/to/your/image.jpg
```

---

## Troubleshooting

### Docker Permission Error
```bash
# Fix: Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### S3 Bucket Not Found
```bash
# Create bucket
aws s3 mb s3://YOUR_S3_BUCKET --region us-east-2
```

### Import Errors
```bash
# Install SageMaker SDK
pip install sagemaker boto3
```

### Endpoint Deployment Fails
- Check IAM role has SageMaker permissions
- Verify instance quotas in your region
- Check CloudWatch logs for detailed errors

---

## Invoking the Endpoint

### Python Example

```python
import boto3
import json
import base64

sagemaker_runtime = boto3.client('sagemaker-runtime', region_name='us-east-2')

# Prepare input
with open('image.jpg', 'rb') as f:
    image_b64 = base64.b64encode(f.read()).decode('utf-8')

payload = {
    'image': image_b64,
    'diameter': 30,
    'denoise': False,
    'blur': False
}

# Upload to S3
s3 = boto3.client('s3')
s3.put_object(
    Bucket='YOUR_S3_BUCKET',
    Key='async-inference/input/request.json',
    Body=json.dumps(payload)
)

# Invoke async endpoint
response = sagemaker_runtime.invoke_endpoint_async(
    EndpointName='fibroblast-detection-endpoint',
    InputLocation='s3://YOUR_S3_BUCKET/async-inference/input/request.json',
    ContentType='application/json'
)

output_location = response['OutputLocation']
print(f"Results: {output_location}")

# Poll for results
import time
while True:
    try:
        result = s3.get_object(
            Bucket='YOUR_S3_BUCKET',
            Key=output_location.split('/')[-1]
        )
        results = json.loads(result['Body'].read())
        break
    except:
        time.sleep(5)
```

---

## Cost Estimate

**Asynchronous Inference:**
- Pay per compute hour used
- Scales to zero when not in use (no idle costs)
- Example: 100 requests/day × 2 min/request ≈ **$50-80/month**

---

## Deploy Gradio Frontend

To host Gradio online with a domain name, see **[GRADIO_DEPLOYMENT.md](./GRADIO_DEPLOYMENT.md)**

**Quick Summary:**
1. Deploy SageMaker endpoint (this guide)
2. Deploy Gradio app to EC2 (see GRADIO_DEPLOYMENT.md)
3. Point domain to EC2
4. Users access via domain → Gradio → SageMaker

---

## Next Steps

1. ✅ Deploy SageMaker endpoint (Step 2 above)
2. ✅ Deploy Gradio frontend (see GRADIO_DEPLOYMENT.md)
3. Monitor endpoint in AWS Console → SageMaker → Endpoints
4. Set up CloudWatch alarms for errors

---

## Support

- AWS SageMaker Docs: https://docs.aws.amazon.com/sagemaker/
- Asynchronous Inference: https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference.html
- Gradio Deployment: See [GRADIO_DEPLOYMENT.md](./GRADIO_DEPLOYMENT.md)