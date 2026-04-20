# Quick Guide: Pay-Per-Use Deployment

**Stop paying $530/month for an idle GPU endpoint!** Use these pay-per-use options instead.

---

## 🎯 Choose Your Option

### Option 1: Serverless (CPU) - For Low Volume API
**Cost:** ~$0.000012/second | **$0 when idle**

```bash
# Deploy serverless endpoint (CPU only, no GPU)
python sagemaker_deploy.py --serverless --image-uri YOUR_ECR_IMAGE_URI
```

✅ Best for: < 100 images/day, real-time API
⚠️ Limitation: CPU only (slower), 4MB max payload

---

### Option 2: Batch Transform (GPU) ⭐ **RECOMMENDED**
**Cost:** ~$0.736/hour | **$0 when idle** | **GPU supported**

```bash
# Step 1: Upload images to S3 (or use --input-dir)
aws s3 sync ./my_images/ s3://YOUR_S3_BUCKET/batch-input/

# Step 2: Run batch job with GPU
python sagemaker_batch_deploy.py \
  --image-uri YOUR_ECR_IMAGE_URI \
  --model-uri s3://YOUR_S3_BUCKET/models/fibroblast-detection-model/model.tar.gz \
  --input-s3 s3://YOUR_S3_BUCKET/batch-input/ \
  --output-s3 s3://YOUR_S3_BUCKET/batch-output/ \
  --monitor

# Or process local directory directly:
python sagemaker_batch_deploy.py \
  --image-uri YOUR_ECR_IMAGE_URI \
  --model-uri s3://YOUR_S3_BUCKET/models/fibroblast-detection-model/model.tar.gz \
  --input-dir ./my_images/ \
  --output-s3 s3://YOUR_S3_BUCKET/batch-output/ \
  --monitor

# Step 3: Download results
aws s3 sync s3://YOUR_S3_BUCKET/batch-output/ ./results/
```

✅ Best for: Batch processing, weekly/daily jobs, full GPU performance
✅ Instance auto-terminates when done

---

## 💰 Cost Comparison

| Usage Pattern | Persistent GPU | Serverless (CPU) | Batch (GPU) |
|---------------|----------------|------------------|-------------|
| **100 images/day** (10s each) | $530/month | $3.60/month | N/A |
| **500 images/week** (1hr job) | $530/month | $14.40/month | $2.94/month ⭐ |
| **1000 images/month** (sporadic) | $530/month | $3.60/month ⭐ | N/A |
| **10,000 images/day** (24/7) | $530/month ⭐ | $360/month | N/A |

---

## 🚀 Complete Setup

### First Time Setup

```bash
# 1. Build and push Docker image to ECR (one-time)
python sagemaker_deploy.py --setup-ecr-only

# This will output your ECR image URI:
# YOUR_AWS_ACCOUNT_ID.dkr.ecr.us-east-2.amazonaws.com/fibroblast-detection:latest
```

### Deploy Serverless Endpoint

```bash
# Deploy serverless (CPU only)
python sagemaker_deploy.py \
  --serverless \
  --skip-ecr \
  --image-uri YOUR_AWS_ACCOUNT_ID.dkr.ecr.us-east-2.amazonaws.com/fibroblast-detection:latest
```

### Run Batch Job (GPU)

```bash
# Process local images with GPU
python sagemaker_batch_deploy.py \
  --image-uri YOUR_AWS_ACCOUNT_ID.dkr.ecr.us-east-2.amazonaws.com/fibroblast-detection:latest \
  --model-uri s3://YOUR_S3_BUCKET/models/fibroblast-detection-model/model.tar.gz \
  --input-dir ./images/ \
  --output-s3 s3://YOUR_S3_BUCKET/results/ \
  --monitor
```

---

## 📊 Monitor Costs

```bash
# Check current costs
aws ce get-cost-and-usage \
  --time-period Start=2026-02-01,End=2026-02-28 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --filter file://filter.json

# filter.json:
{
  "Dimensions": {
    "Key": "SERVICE",
    "Values": ["Amazon SageMaker"]
  }
}
```

---

## 🛑 Stop Wasting Money

### Delete Persistent Endpoint

```bash
# If you have a persistent endpoint running, delete it NOW
python cleanup_failed_endpoint.py

# Or manually:
aws sagemaker delete-endpoint --endpoint-name fibroblast-detection-endpoint
aws sagemaker delete-endpoint-config --endpoint-config-name fibroblast-detection-endpoint
```

**Savings:** ~$530/month → $3-15/month with pay-per-use

---

## ❓ Which Option Should I Use?

### Use **Serverless (CPU)** if:
- ✅ You need real-time API responses
- ✅ Low volume (< 100 images/day)
- ✅ CPU performance is acceptable
- ✅ Images are < 4MB

### Use **Batch Transform (GPU)** if:
- ✅ Processing batches of images
- ✅ Need full GPU performance
- ✅ Weekly/daily scheduled jobs
- ✅ Large batches (100+ images)

### Use **Persistent GPU Endpoint** if:
- ✅ High volume 24/7 (> 5000 images/day)
- ✅ Need < 1 second response time
- ✅ Unpredictable burst traffic

---

## 📝 Example Workflows

### Daily Batch Processing

```bash
#!/bin/bash
# daily_process.sh - Run this in a cron job

# Process yesterday's images
python sagemaker_batch_deploy.py \
  --image-uri $ECR_IMAGE_URI \
  --model-uri $MODEL_URI \
  --input-dir /data/images/$(date -d yesterday +%Y%m%d)/ \
  --output-s3 s3://bucket/results/$(date -d yesterday +%Y%m%d)/ \
  --monitor

# Download results
aws s3 sync s3://bucket/results/$(date -d yesterday +%Y%m%d)/ /results/

# Cost: ~$0.736/hour × (processing time in hours)
```

### On-Demand API (Serverless)

```python
import boto3
import json
import base64

# One-time setup: deploy serverless endpoint
# python sagemaker_deploy.py --serverless --image-uri ...

# Then use it whenever needed (pay only for actual usage)
runtime = boto3.client('sagemaker-runtime', region_name='us-east-2')

with open('image.jpg', 'rb') as f:
    image_b64 = base64.b64encode(f.read()).decode('utf-8')

payload = {
    'image': image_b64,
    'diameter': 30,
    'denoise': False,
    'blur': False
}

response = runtime.invoke_endpoint(
    EndpointName='fibroblast-detection-endpoint',
    Body=json.dumps(payload),
    ContentType='application/json'
)

result = json.loads(response['Body'].read())
print(result)

# Cost: ~$0.000012/second of processing time
```

---

## 🔧 Troubleshooting

### Batch Job Fails
```bash
# Check job status
aws sagemaker describe-transform-job --transform-job-name JOB_NAME

# Check CloudWatch logs
aws logs tail /aws/sagemaker/TransformJobs/JOB_NAME --follow
```

### Serverless Cold Start Too Slow
- First request after idle takes 10-60 seconds
- Consider batch transform instead for large jobs
- Or keep endpoint warm with scheduled pings

### Out of Memory
```bash
# Use larger instance for batch jobs
python sagemaker_batch_deploy.py \
  --instance-type ml.g4dn.2xlarge \  # More memory
  ...
```

---

## 📚 More Details

See [PAY_PER_USE_OPTIONS.md](PAY_PER_USE_OPTIONS.md) for complete documentation.
